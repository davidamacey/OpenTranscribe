"""
Speaker Clustering Service for pre-clustering unnamed speakers across files.

Uses a hybrid approach:
- Real-time: kNN against cluster centroids in OpenSearch + threshold assignment
- Batch: GPU-accelerated cosine similarity (PyTorch) with AHC (complete linkage)

Cluster centroids are stored in OpenSearch with document_type="cluster".
"""

import logging
import math
from collections import defaultdict
from typing import Any
from uuid import uuid4

import numpy as np
import torch
from scipy.cluster.hierarchy import fcluster
from scipy.cluster.hierarchy import linkage
from scipy.spatial.distance import squareform
from sqlalchemy import case
from sqlalchemy.orm import Session
from sqlalchemy.orm import joinedload
from sqlalchemy.orm import subqueryload

from app.models.media import Speaker
from app.models.media import SpeakerCluster
from app.models.media import SpeakerClusterMember
from app.models.media import SpeakerProfile
from app.models.media import TranscriptSegment

logger = logging.getLogger(__name__)

# Clustering thresholds
# With complete linkage, 0.75 nearly guarantees same speaker identity
CLUSTER_ASSIGNMENT_THRESHOLD = 0.75
# Rows of the similarity chunk processed at a time.
# 500 rows x N cols x 4 bytes keeps each chunk under ~30 MB
# even at 15 000 unlabeled speakers.
SIM_CHUNK = 500


class SpeakerClusteringService:
    """Service for clustering speakers across media files."""

    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # Real-time cluster assignment (called after transcription)
    # ------------------------------------------------------------------

    def find_or_create_cluster(
        self,
        speaker_id: int,
        user_id: int,
        embedding: list[float],
        threshold: float = CLUSTER_ASSIGNMENT_THRESHOLD,
    ) -> SpeakerCluster | None:
        """Assign a speaker to an existing cluster or create a new singleton.

        Uses kNN search against cluster centroids in OpenSearch.

        Args:
            speaker_id: Database ID of the speaker.
            user_id: Owner user ID.
            embedding: L2-normalized speaker embedding vector.
            threshold: Minimum cosine similarity to join an existing cluster.

        Returns:
            The cluster the speaker was assigned to, or None on error.
        """
        try:
            speaker = (
                self.db.query(Speaker).filter(Speaker.id == speaker_id).with_for_update().first()
            )
            if not speaker:
                logger.warning("Speaker %s not found", speaker_id)
                return None

            # Skip if already in a cluster
            if speaker.cluster_id:
                cluster = (
                    self.db.query(SpeakerCluster)
                    .filter(SpeakerCluster.id == speaker.cluster_id)
                    .first()
                )
                return cluster  # type: ignore[no-any-return]

            # Search for matching cluster centroids
            from app.services.opensearch_service import find_matching_clusters

            matches = find_matching_clusters(embedding, user_id, k=5, threshold=threshold)

            if matches:
                best = matches[0]
                margin = best["similarity"] - matches[1]["similarity"] if len(matches) > 1 else 1.0
                cluster_uuid = best["cluster_uuid"]
                cluster = (
                    self.db.query(SpeakerCluster)
                    .filter(
                        SpeakerCluster.uuid == cluster_uuid,
                        SpeakerCluster.user_id == user_id,
                    )
                    .first()
                )
                if cluster:
                    self._add_speaker_to_cluster(
                        speaker, cluster, best["similarity"], margin=margin
                    )
                    # Auto-propagate profile if cluster is promoted
                    if cluster.promoted_to_profile_id:
                        speaker.profile_id = cluster.promoted_to_profile_id
                        profile = (
                            self.db.query(SpeakerProfile)
                            .filter(SpeakerProfile.id == cluster.promoted_to_profile_id)
                            .first()
                        )
                        if profile:
                            speaker.display_name = profile.name
                            speaker.verified = True
                    self._update_cluster_centroid(cluster, user_id)
                    return cluster  # type: ignore[no-any-return]

            # No match — create a new singleton cluster
            cluster = self._create_singleton_cluster(speaker, user_id, embedding)
            return cluster  # type: ignore[no-any-return]

        except Exception as e:
            logger.error("Error in find_or_create_cluster for speaker %s: %s", speaker_id, e)
            self.db.rollback()
            return None

    def cluster_speakers_for_file(
        self,
        media_file_id: int,
        user_id: int,
    ) -> list[SpeakerCluster]:
        """Cluster all speakers in a media file after transcription.

        Args:
            media_file_id: Media file ID.
            user_id: Owner user ID.

        Returns:
            List of clusters speakers were assigned to.
        """
        speakers = (
            self.db.query(Speaker)
            .filter(
                Speaker.media_file_id == media_file_id,
                Speaker.user_id == user_id,
            )
            .all()
        )

        if not speakers:
            logger.info("No speakers found for media file %s", media_file_id)
            return []

        clusters: list[SpeakerCluster] = []
        for speaker in speakers:
            embedding = self._get_speaker_embedding(speaker)
            if embedding is None:
                continue
            cluster = self.find_or_create_cluster(int(speaker.id), user_id, embedding)
            if cluster:
                clusters.append(cluster)

        self.db.commit()
        return clusters

    # ------------------------------------------------------------------
    # Batch clustering (on-demand)
    # ------------------------------------------------------------------

    def batch_recluster(
        self,
        user_id: int,
        threshold: float = CLUSTER_ASSIGNMENT_THRESHOLD,
        progress_callback: Any | None = None,
    ) -> dict[str, Any]:
        """Two-phase re-clustering: profile-aware grouping then AHC discovery.

        Phase 1 (deterministic): Group speakers that already share the same
        verified profile_id into clusters — no embedding math required.

        Phase 2 (similarity): For remaining unlabeled speakers, build a full
        cosine similarity matrix from OpenSearch embeddings and discover
        clusters via AHC (Agglomerative Hierarchical Clustering) with
        complete linkage.

        Args:
            user_id: Owner user ID.
            threshold: Cosine similarity threshold for Phase 2.
            progress_callback: Optional callable(step, total, message, progress)
                for reporting progress to the caller.

        Returns:
            Summary dict with cluster counts and stats.
        """
        try:
            if threshold < 0.5 or threshold > 0.95:
                raise ValueError(f"Threshold must be in [0.5, 0.95], got {threshold}")

            from app.services.opensearch_service import iter_speaker_embeddings

            def _report(step: int, total: int, msg: str, pct: float) -> None:
                if progress_callback:
                    try:
                        progress_callback(step, total, msg, pct)
                    except Exception as e:
                        logger.debug("Progress callback failed: %s", e)

            # ----------------------------------------------------------
            # Step 1: Clear ALL old clusters (including promoted)
            # Phase 1 will recreate promoted clusters from profiles.
            # ----------------------------------------------------------
            _report(1, 5, "Clearing old clusters...", 0.05)
            old_clusters = (
                self.db.query(SpeakerCluster).filter(SpeakerCluster.user_id == user_id).all()
            )
            for oc in old_clusters:
                # Remove centroid from OpenSearch
                try:
                    from app.services.opensearch_service import delete_cluster_embedding

                    delete_cluster_embedding(str(oc.uuid))
                except Exception:
                    logger.debug("Failed to remove centroid for cluster %s", oc.uuid)
                self.db.query(Speaker).filter(Speaker.cluster_id == oc.id).update(
                    {"cluster_id": None}
                )
                self.db.delete(oc)
            self.db.flush()

            clusters_created = 0
            speakers_assigned = 0
            centroid_failures = 0

            # ----------------------------------------------------------
            # Step 2 (Phase 1): Profile-based clustering
            # Pure DB query — no embeddings loaded.
            # ----------------------------------------------------------
            _report(2, 5, "Grouping by verified profiles...", 0.15)
            profile_speakers = (
                self.db.query(Speaker)
                .filter(
                    Speaker.user_id == user_id,
                    Speaker.profile_id.isnot(None),
                )
                .all()
            )

            profile_groups: dict[int, list[Speaker]] = defaultdict(list)
            profiled_speaker_ids: set[int] = set()
            for spk in profile_speakers:
                profile_groups[int(spk.profile_id)].append(spk)
                profiled_speaker_ids.add(int(spk.id))

            # Embedding cache: speaker_id -> embedding (reused across phases)
            emb_cache: dict[int, list[float]] = {}

            phase1_profile_clusters: dict[str, SpeakerCluster] = {}
            for profile_id, members in profile_groups.items():
                if len(members) < 2:
                    continue

                profile = (
                    self.db.query(SpeakerProfile).filter(SpeakerProfile.id == profile_id).first()
                )
                cluster = SpeakerCluster(
                    uuid=uuid4(),
                    user_id=user_id,
                    member_count=0,
                    label=profile.name if profile else None,
                    promoted_to_profile_id=profile.id if profile else None,
                )
                self.db.add(cluster)
                self.db.flush()
                if profile:
                    profile.source_cluster_id = cluster.id

                self._bulk_add_speakers_to_cluster(members, cluster, 1.0)
                speakers_assigned += len(members)

                self._update_cluster_centroid(cluster, user_id, refresh=False)
                clusters_created += 1
                phase1_profile_clusters[str(cluster.uuid)] = cluster

            profile_clusters = clusters_created
            profile_assigned = speakers_assigned
            logger.info(
                "Phase 1 (profile grouping): %d clusters, %d speakers (%d profiles) for user %d",
                profile_clusters,
                profile_assigned,
                len(profile_groups),
                user_id,
            )

            # ----------------------------------------------------------
            # Step 3 (Phase 2): GPU-accelerated cosine similarity + AHC
            #
            # PyTorch on CUDA for fast matrix operations, CPU fallback.
            #
            # a) Query unlabeled speaker UUIDs from DB
            # b) Fetch embeddings from OpenSearch -> PyTorch tensor
            # c) F.normalize (L2) on device
            # d) Chunked matmul on GPU: chunk @ M.T  (SIM_CHUNK x N)
            #    -> write results to CPU float32 sim_full np array
            # e) AHC (complete linkage) on distance matrix
            #
            # GPU memory budget (worst case 15k x 512-dim float16):
            #   M           = 15000 x 512 x 2  ~  15 MB VRAM
            #   M.T         = transposed copy     ~  15 MB VRAM
            #   sim chunk   = 2000 x 15000 x 2  ~  60 MB VRAM
            #   peak total  ~  90 MB VRAM (trivial for any GPU)
            # ----------------------------------------------------------
            _report(3, 5, "Loading unlabeled embeddings...", 0.25)
            unlabeled_rows = (
                self.db.query(Speaker.id, Speaker.uuid)
                .filter(
                    Speaker.user_id == user_id,
                    Speaker.profile_id.is_(None),
                )
                .all()
            )
            unlabeled_uuid_to_id: dict[str, int] = {str(r.uuid): int(r.id) for r in unlabeled_rows}
            unlabeled_uuids = list(unlabeled_uuid_to_id.keys())
            total_unlabeled = len(unlabeled_uuids)

            logger.info(
                "Phase 2: %d unlabeled speakers for user %d (threshold=%.2f)",
                total_unlabeled,
                user_id,
                threshold,
            )

            # Collect embeddings into aligned index arrays
            ordered_ids: list[int] = []
            emb_rows: list[list[float]] = []

            for batch in iter_speaker_embeddings(
                user_id, speaker_uuids=unlabeled_uuids, batch_size=500
            ):
                for item in batch:
                    sid = unlabeled_uuid_to_id.get(item["speaker_uuid"])
                    if sid is not None:
                        ordered_ids.append(sid)
                        emb_rows.append(item["embedding"])

            # Cache embeddings so centroid computation skips OpenSearch
            for i, sid in enumerate(ordered_ids):
                emb_cache[sid] = emb_rows[i]

            # Validate embedding dimensions are consistent
            if emb_rows:
                expected_dim = len(emb_rows[0])
                valid_indices = [i for i, e in enumerate(emb_rows) if len(e) == expected_dim]
                if len(valid_indices) < len(emb_rows):
                    skipped = len(emb_rows) - len(valid_indices)
                    logger.warning(
                        "Skipped %d embeddings with mismatched dimensions (expected %d)",
                        skipped,
                        expected_dim,
                    )
                    emb_rows = [emb_rows[i] for i in valid_indices]
                    ordered_ids = [ordered_ids[i] for i in valid_indices]

            n = len(emb_rows)

            if n > 1:
                # Use first available CUDA device (Docker maps the correct
                # host GPU via device_ids in docker-compose.gpu.yml, so
                # cuda:0 inside the container is always the right device
                # regardless of host GPU topology or scaling config).
                device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
                logger.info(
                    "Phase 2: computing similarities for %d speakers on %s (dim=%d)",
                    n,
                    device,
                    len(emb_rows[0]),
                )

                _report(4, 5, "Computing cosine similarities...", 0.4)

                # Pre-allocate CPU float32 array for full similarity matrix
                emb_matrix = np.array(emb_rows, dtype=np.float32)
                del emb_rows
                sim_full = np.empty((n, n), dtype=np.float32)

                try:
                    # Build (N, D) fp16 tensor on device for fast matmul
                    M = torch.tensor(
                        emb_matrix,
                        dtype=torch.float16,
                        device=device,
                    )
                    del emb_matrix

                    # Safe L2-normalize: clamp norms to avoid NaN from zero-length embeddings
                    norms = M.norm(dim=1, keepdim=True).clamp(min=1e-8)
                    M = M / norms

                    # Pre-transpose once — .T is not contiguous, make it so
                    MT = M.T.contiguous()

                    # Larger chunks on GPU (much more VRAM headroom)
                    sim_chunk = 2000 if device.type == "cuda" else SIM_CHUNK
                    total_chunks = math.ceil(n / sim_chunk)

                    for ci in range(total_chunks):
                        start = ci * sim_chunk
                        end = min(start + sim_chunk, n)

                        # (chunk, D) @ (D, N) -> (chunk, N) cosine sims
                        sim_block = torch.mm(M[start:end], MT)
                        sim_full[start:end] = sim_block.float().cpu().numpy()
                        del sim_block

                        _report(
                            4,
                            5,
                            "Computing cosine similarities...",
                            0.4 + 0.3 * (ci + 1) / total_chunks,
                        )

                    del M, MT
                finally:
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

                # --- AHC with complete linkage ---
                _report(4, 5, "Clustering with AHC (complete linkage)...", 0.75)

                # Ensure diagonal is exactly 1.0 and matrix is symmetric
                np.fill_diagonal(sim_full, 1.0)
                sim_full = np.maximum(sim_full, sim_full.T)

                # Convert similarity to distance
                dist = 1.0 - sim_full
                np.clip(dist, 0.0, 2.0, out=dist)
                np.fill_diagonal(dist, 0.0)
                del sim_full

                # scipy AHC
                condensed = squareform(dist, checks=False)
                del dist
                Z = linkage(condensed, method="complete")
                del condensed
                labels = fcluster(Z, t=1.0 - threshold, criterion="distance")
                del Z

                # Build groups from fcluster labels
                groups: dict[int, list[int]] = defaultdict(list)
                for idx, label in enumerate(labels):
                    groups[int(label)].append(ordered_ids[idx])
                del labels

                logger.info(
                    "Phase 2 AHC: %d groups (>= 2 members: %d) from %d speakers",
                    len(groups),
                    sum(1 for g in groups.values() if len(g) >= 2),
                    n,
                )
            else:
                del emb_rows
                groups = {}

            # ----------------------------------------------------------
            # Step 5: Create cluster records from AHC groups
            # ----------------------------------------------------------
            _report(5, 5, "Creating cluster records...", 0.9)
            sim_clusters = 0
            sim_assigned = 0

            # Batch-fetch all speakers that belong to multi-member groups
            multi_member_ids: list[int] = []
            for member_ids in groups.values():
                if len(member_ids) >= 2:
                    multi_member_ids.extend(member_ids)

            speakers_by_id: dict[int, Speaker] = {}
            if multi_member_ids:
                batch_speakers = (
                    self.db.query(Speaker).filter(Speaker.id.in_(multi_member_ids)).all()
                )
                speakers_by_id = {int(s.id): s for s in batch_speakers}

            from app.services.opensearch_service import store_cluster_embedding

            for _label, member_ids in groups.items():
                if len(member_ids) < 2:
                    continue

                cluster = SpeakerCluster(
                    uuid=uuid4(),
                    user_id=user_id,
                    member_count=0,
                )
                self.db.add(cluster)
                self.db.flush()

                # Compute centroid and per-member confidence from cached
                # embeddings before adding members to cluster
                member_embs = [emb_cache[sid] for sid in member_ids if sid in emb_cache]
                per_member_conf: dict[int, float] = {}
                if member_embs:
                    arr = np.array(member_embs, dtype=np.float32)
                    centroid = np.mean(arr, axis=0)
                    c_norm = np.linalg.norm(centroid)
                    if c_norm > 1e-8:
                        centroid = centroid / c_norm
                    # Cosine similarity of each member to the L2-normalized centroid
                    arr_norms = np.linalg.norm(arr, axis=1, keepdims=True).clip(1e-8)
                    arr_normed = arr / arr_norms
                    sims = arr_normed @ centroid  # centroid already L2-normalized
                    emb_idx = 0
                    for sid in member_ids:
                        if sid in emb_cache:
                            per_member_conf[sid] = float(max(0.0, min(1.0, sims[emb_idx])))
                            emb_idx += 1

                # Bulk-add all members with per-member confidence
                cluster_speakers = [
                    speakers_by_id[sid] for sid in member_ids if sid in speakers_by_id
                ]
                added = self._bulk_add_speakers_to_cluster(
                    cluster_speakers,
                    cluster,
                    per_member_conf or 0.0,
                )
                sim_assigned += added

                if member_embs:
                    # Quality score: average centroid similarity (same metric
                    # shown per-member, so the cluster score is consistent
                    # with individual member scores users see in the UI).
                    # min_similarity: tightest pairwise cosine similarity
                    # (worst-case pair within the cluster).
                    if len(member_embs) >= 2:
                        normed = arr / np.linalg.norm(
                            arr,
                            axis=1,
                            keepdims=True,
                        ).clip(1e-8)
                        # Average centroid similarity for quality score
                        cluster.quality_score = float(  # type: ignore[assignment]
                            np.mean(normed @ centroid)
                        )
                        # Min pairwise for worst-case indicator
                        sim_mat = normed @ normed.T
                        iu = np.triu_indices(len(member_embs), k=1)
                        cluster.min_similarity = float(  # type: ignore[assignment]
                            np.min(sim_mat[iu])
                        )
                    else:
                        cluster.quality_score = 1.0  # type: ignore[assignment]
                        cluster.min_similarity = 1.0  # type: ignore[assignment]

                    cluster.representative_speaker_id = member_ids[0]  # type: ignore[assignment]

                    try:
                        store_cluster_embedding(
                            cluster_uuid=str(cluster.uuid),
                            user_id=user_id,
                            embedding=centroid.tolist(),
                            label=cluster.label,
                            refresh=False,
                        )
                    except Exception as e:
                        logger.warning(
                            "Could not store centroid for cluster %s: %s",
                            cluster.uuid,
                            e,
                        )
                        centroid_failures += 1

                sim_clusters += 1

            clusters_created += sim_clusters
            speakers_assigned += sim_assigned

            # ----------------------------------------------------------
            # Post-clustering validation: verify all pairwise similarities
            # within each AHC cluster meet the threshold. Log warnings
            # for any violating pairs (indicates numerical edge cases).
            # ----------------------------------------------------------
            if sim_clusters > 0 and emb_cache:
                violations = 0
                for _lbl, member_ids_v in groups.items():
                    if len(member_ids_v) < 2:
                        continue
                    vecs = [emb_cache[sid] for sid in member_ids_v if sid in emb_cache]
                    if len(vecs) < 2:
                        continue
                    varr = np.array(vecs, dtype=np.float32)
                    vnorms = np.linalg.norm(varr, axis=1, keepdims=True).clip(1e-8)
                    varr_n = varr / vnorms
                    sim_mat = varr_n @ varr_n.T
                    iu = np.triu_indices(len(vecs), k=1)
                    min_sim = float(np.min(sim_mat[iu]))
                    if min_sim < threshold - 0.01:  # 1% tolerance
                        violations += 1
                        logger.warning(
                            "Cluster validation: group with %d members "
                            "has min pairwise similarity %.4f (threshold=%.2f)",
                            len(member_ids_v),
                            min_sim,
                            threshold,
                        )
                if violations:
                    logger.warning(
                        "Post-clustering validation: %d/%d clusters have sub-threshold pairs",
                        violations,
                        sim_clusters,
                    )
                else:
                    logger.info(
                        "Post-clustering validation: all %d AHC clusters "
                        "pass threshold check (>=%.2f)",
                        sim_clusters,
                        threshold,
                    )

            # Single index refresh after all batch centroid writes
            # (must happen BEFORE Phase 2.5 kNN queries)
            try:
                from app.services.opensearch_service import get_active_speaker_index
                from app.services.opensearch_service import opensearch_client

                active_index = get_active_speaker_index()
                if opensearch_client:
                    opensearch_client.indices.refresh(index=active_index)
            except Exception as e:
                logger.warning("Failed to refresh speaker index: %s", e)

            # ----------------------------------------------------------
            # Phase 2.5: Match singletons against profile centroids
            # ----------------------------------------------------------
            grouped_ids = set(multi_member_ids) if multi_member_ids else set()
            singleton_ids = [sid for sid in ordered_ids if sid not in grouped_ids]
            if singleton_ids and profile_clusters > 0:
                from app.services.opensearch_service import find_matching_clusters

                # Build map: include Phase 1 clusters + any pre-existing promoted clusters
                profile_cluster_map: dict[str, SpeakerCluster] = dict(phase1_profile_clusters)
                for pc in (
                    self.db.query(SpeakerCluster)
                    .filter(
                        SpeakerCluster.user_id == user_id,
                        SpeakerCluster.promoted_to_profile_id.isnot(None),
                    )
                    .all()
                ):
                    profile_cluster_map[str(pc.uuid)] = pc

                if profile_cluster_map:
                    singleton_speakers = (
                        self.db.query(Speaker).filter(Speaker.id.in_(singleton_ids)).all()
                    )
                    matched_singletons = 0
                    for spk in singleton_speakers:
                        emb = emb_cache.get(int(spk.id))
                        if emb is None:
                            continue
                        matches = find_matching_clusters(
                            emb,
                            user_id,
                            k=1,
                            threshold=threshold,
                        )
                        if matches:
                            pc = profile_cluster_map.get(matches[0]["cluster_uuid"])
                            if pc:
                                self._add_speaker_to_cluster(spk, pc, matches[0]["similarity"])
                                speakers_assigned += 1
                                matched_singletons += 1
                    if matched_singletons:
                        logger.info(
                            "Phase 2.5: matched %d singletons to profile clusters",
                            matched_singletons,
                        )

            total_speakers = len(profiled_speaker_ids) + total_unlabeled
            singletons = total_speakers - speakers_assigned

            # ----------------------------------------------------------
            # Compute separation scores for all multi-member clusters
            # ----------------------------------------------------------
            all_cluster_centroids: list[np.ndarray] = []
            all_clusters_for_sep: list[SpeakerCluster] = []
            for cluster_record in (
                self.db.query(SpeakerCluster)
                .filter(
                    SpeakerCluster.user_id == user_id,
                    SpeakerCluster.member_count >= 2,
                )
                .all()
            ):
                member_ids_q = [
                    int(m.speaker_id)
                    for m in self.db.query(SpeakerClusterMember)
                    .filter(SpeakerClusterMember.cluster_id == cluster_record.id)
                    .all()
                ]
                member_embs_sep = [emb_cache[sid] for sid in member_ids_q if sid in emb_cache]
                if member_embs_sep:
                    c = np.mean(np.array(member_embs_sep, dtype=np.float32), axis=0)
                    c_norm = np.linalg.norm(c)
                    if c_norm > 1e-8:
                        c = c / c_norm
                        all_cluster_centroids.append(c)
                        all_clusters_for_sep.append(cluster_record)

            if len(all_cluster_centroids) >= 2:
                centroid_matrix = np.array(all_cluster_centroids, dtype=np.float32)
                c_sim = centroid_matrix @ centroid_matrix.T
                np.fill_diagonal(c_sim, -1.0)  # Exclude self-similarity
                for i, cr in enumerate(all_clusters_for_sep):
                    max_neighbor_sim = float(np.max(c_sim[i]))
                    cr.separation_score = round(  # type: ignore[assignment]
                        1.0 - max_neighbor_sim, 4
                    )

            self.db.commit()
            logger.info(
                "Re-clustering complete for user %d: "
                "%d profile clusters (%d speakers), "
                "%d similarity clusters (%d speakers), "
                "%d singletons",
                user_id,
                profile_clusters,
                profile_assigned,
                sim_clusters,
                sim_assigned,
                singletons,
            )

            status = "completed"
            if (
                centroid_failures > 0
                and clusters_created > 0
                and centroid_failures / clusters_created > 0.1
            ):
                status = "partial_failure"

            return {
                "status": status,
                "total_speakers": total_speakers,
                "profile_clusters": profile_clusters,
                "profile_speakers_assigned": profile_assigned,
                "similarity_clusters": sim_clusters,
                "similarity_speakers_assigned": sim_assigned,
                "clusters_created": clusters_created,
                "speakers_assigned": speakers_assigned,
                "singletons": singletons,
                "centroid_failures": centroid_failures,
            }

        except Exception as e:
            logger.error("Error in batch re-clustering: %s", e)
            self.db.rollback()
            raise

    # ------------------------------------------------------------------
    # Cluster operations (merge, split, promote)
    # ------------------------------------------------------------------

    def merge_clusters(
        self,
        source_uuid: str,
        target_uuid: str,
        user_id: int,
    ) -> SpeakerCluster | None:
        """Merge source cluster into target. All members move to target.

        Args:
            source_uuid: UUID of the cluster to dissolve.
            target_uuid: UUID of the cluster to absorb members.
            user_id: Owner user ID.

        Returns:
            The target cluster after merge, or None on error.
        """
        try:
            # Lock both clusters in consistent UUID order to prevent deadlocks
            first_uuid, second_uuid = sorted([source_uuid, target_uuid])
            self.db.query(SpeakerCluster).filter(
                SpeakerCluster.uuid == first_uuid,
                SpeakerCluster.user_id == user_id,
            ).with_for_update().first()
            if first_uuid != second_uuid:
                self.db.query(SpeakerCluster).filter(
                    SpeakerCluster.uuid == second_uuid,
                    SpeakerCluster.user_id == user_id,
                ).with_for_update().first()

            source = (
                self.db.query(SpeakerCluster)
                .filter(SpeakerCluster.uuid == source_uuid, SpeakerCluster.user_id == user_id)
                .first()
            )
            target = (
                self.db.query(SpeakerCluster)
                .filter(SpeakerCluster.uuid == target_uuid, SpeakerCluster.user_id == user_id)
                .first()
            )

            if not source or not target:
                logger.warning(
                    "Cluster not found for merge: source=%s, target=%s", source_uuid, target_uuid
                )
                return None

            # Move members
            source_members = (
                self.db.query(SpeakerClusterMember)
                .filter(SpeakerClusterMember.cluster_id == source.id)
                .all()
            )

            # Batch-fetch existing speaker_ids in target to avoid per-member queries
            existing_speaker_ids = {
                int(r.speaker_id)
                for r in self.db.query(SpeakerClusterMember.speaker_id)
                .filter(SpeakerClusterMember.cluster_id == target.id)
                .all()
            }

            # Batch-fetch all speakers referenced by source members
            member_speaker_ids = [int(m.speaker_id) for m in source_members]
            speakers_by_id = {
                int(s.id): s
                for s in self.db.query(Speaker).filter(Speaker.id.in_(member_speaker_ids)).all()
            }

            for member in source_members:
                if int(member.speaker_id) in existing_speaker_ids:
                    self.db.delete(member)
                else:
                    member.cluster_id = target.id  # type: ignore[assignment]

                # Update speaker FK
                speaker = speakers_by_id.get(int(member.speaker_id))
                if speaker:
                    speaker.cluster_id = target.id  # type: ignore[assignment]

            # Update target count
            target.member_count = (  # type: ignore[assignment]
                self.db.query(SpeakerClusterMember)
                .filter(SpeakerClusterMember.cluster_id == target.id)
                .count()
            )

            # Remove source cluster centroid from OpenSearch
            try:
                from app.services.opensearch_service import delete_cluster_embedding

                delete_cluster_embedding(str(source.uuid))
            except Exception as e:
                logger.warning("Could not delete source cluster embedding: %s", e)

            self.db.delete(source)
            self._update_cluster_centroid(target, user_id)
            self.db.commit()

            logger.info("Merged cluster %s into %s", source_uuid, target_uuid)
            return target  # type: ignore[no-any-return]

        except Exception as e:
            logger.error("Error merging clusters: %s", e)
            self.db.rollback()
            return None

    def split_cluster(
        self,
        cluster_uuid: str,
        speaker_uuids: list[str],
        user_id: int,
    ) -> SpeakerCluster | None:
        """Split specified speakers into a new cluster.

        Args:
            cluster_uuid: UUID of the source cluster.
            speaker_uuids: UUIDs of speakers to move to the new cluster.
            user_id: Owner user ID.

        Returns:
            The newly created cluster, or None on error.
        """
        try:
            source = (
                self.db.query(SpeakerCluster)
                .filter(SpeakerCluster.uuid == cluster_uuid, SpeakerCluster.user_id == user_id)
                .with_for_update()
                .first()
            )
            if not source:
                logger.warning("Cluster %s not found", cluster_uuid)
                return None

            # Resolve speaker IDs
            speakers_to_move = (
                self.db.query(Speaker)
                .filter(Speaker.uuid.in_(speaker_uuids), Speaker.user_id == user_id)
                .all()
            )
            if not speakers_to_move:
                logger.warning("No valid speakers to split")
                return None

            speakers_to_move = [s for s in speakers_to_move if s.cluster_id == source.id]
            if not speakers_to_move:
                logger.warning("No speakers from source cluster to split")
                return None

            # Create new cluster
            new_cluster = SpeakerCluster(
                uuid=uuid4(),
                user_id=user_id,
                member_count=0,
            )
            self.db.add(new_cluster)
            self.db.flush()

            # Move members
            for speaker in speakers_to_move:
                # Remove from source membership
                self.db.query(SpeakerClusterMember).filter(
                    SpeakerClusterMember.cluster_id == source.id,
                    SpeakerClusterMember.speaker_id == speaker.id,
                ).delete()

                # Add to new cluster
                member = SpeakerClusterMember(
                    uuid=uuid4(),
                    cluster_id=new_cluster.id,
                    speaker_id=speaker.id,
                    confidence=0.0,
                )
                self.db.add(member)
                speaker.cluster_id = new_cluster.id  # type: ignore[assignment]

            # Update counts
            new_cluster.member_count = len(speakers_to_move)  # type: ignore[assignment]
            source.member_count = (  # type: ignore[assignment]
                self.db.query(SpeakerClusterMember)
                .filter(SpeakerClusterMember.cluster_id == source.id)
                .count()
            )

            # Update centroids
            self._update_cluster_centroid(source, user_id)
            self._update_cluster_centroid(new_cluster, user_id)

            # Delete source if empty (fresh count to avoid stale ORM attribute)
            remaining = (
                self.db.query(SpeakerClusterMember)
                .filter(SpeakerClusterMember.cluster_id == source.id)
                .count()
            )
            if remaining == 0:
                try:
                    from app.services.opensearch_service import delete_cluster_embedding

                    delete_cluster_embedding(str(source.uuid))
                except Exception:
                    logger.debug("Failed to remove cluster embedding from OpenSearch")
                self.db.delete(source)

            self.db.commit()
            logger.info("Split %d speakers from cluster %s", len(speakers_to_move), cluster_uuid)
            return new_cluster

        except Exception as e:
            logger.error("Error splitting cluster: %s", e)
            self.db.rollback()
            return None

    def promote_cluster_to_profile(
        self,
        cluster_uuid: str,
        name: str,
        user_id: int,
        description: str | None = None,
    ) -> SpeakerProfile | None:
        """Convert a cluster to a SpeakerProfile and assign all members.

        Args:
            cluster_uuid: UUID of the cluster to promote.
            name: Name for the new profile.
            user_id: Owner user ID.
            description: Optional profile description.

        Returns:
            The created SpeakerProfile, or None on error.
        """
        try:
            cluster = (
                self.db.query(SpeakerCluster)
                .filter(SpeakerCluster.uuid == cluster_uuid, SpeakerCluster.user_id == user_id)
                .first()
            )
            if not cluster:
                logger.warning("Cluster %s not found", cluster_uuid)
                return None

            if cluster.promoted_to_profile_id:
                existing = (
                    self.db.query(SpeakerProfile)
                    .filter(SpeakerProfile.id == cluster.promoted_to_profile_id)
                    .first()
                )
                if existing:
                    logger.info(
                        "Cluster %s already promoted to profile %s", cluster_uuid, existing.uuid
                    )
                    return existing  # type: ignore[no-any-return]

            # Create profile
            profile = SpeakerProfile(
                uuid=uuid4(),
                user_id=user_id,
                name=name,
                description=description,
            )
            self.db.add(profile)
            self.db.flush()

            # Link cluster and sync label
            cluster.promoted_to_profile_id = profile.id  # type: ignore[assignment]
            if not cluster.label:
                cluster.label = name  # type: ignore[assignment]

            # Assign all member speakers to the profile
            members = (
                self.db.query(SpeakerClusterMember)
                .filter(SpeakerClusterMember.cluster_id == cluster.id)
                .all()
            )

            # Batch-fetch all speakers to avoid per-member queries
            speaker_ids = [int(m.speaker_id) for m in members]
            speakers_by_id = {
                int(s.id): s
                for s in self.db.query(Speaker).filter(Speaker.id.in_(speaker_ids)).all()
            }

            for member in members:
                speaker = speakers_by_id.get(int(member.speaker_id))
                if speaker:
                    speaker.profile_id = profile.id  # type: ignore[assignment]
                    speaker.display_name = name  # type: ignore[assignment]
                    speaker.verified = True  # type: ignore[assignment]

            # Update profile embedding
            from app.services.profile_embedding_service import ProfileEmbeddingService

            self.db.commit()
            ProfileEmbeddingService.update_profile_embedding(self.db, int(profile.id))

            logger.info(
                "Promoted cluster %s to profile '%s' (%d speakers)",
                cluster_uuid,
                name,
                len(members),
            )
            return profile

        except Exception as e:
            logger.error("Error promoting cluster to profile: %s", e)
            self.db.rollback()
            return None

    # ------------------------------------------------------------------
    # Inbox / unverified speakers
    # ------------------------------------------------------------------

    def get_unverified_speakers(
        self,
        user_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        """Get paginated list of unverified speakers across all files.

        Prioritized by: cluster size (larger first), then suggestion confidence.

        Args:
            user_id: Owner user ID.
            page: Page number (1-based).
            per_page: Items per page.

        Returns:
            Dict with items, total, page, per_page, pages.
        """
        query = (
            self.db.query(Speaker)
            .options(
                joinedload(Speaker.media_file),
                joinedload(Speaker.cluster),
            )
            .filter(
                Speaker.user_id == user_id,
                Speaker.verified.is_(False),
                Speaker.profile_id.is_(None),
            )
            .outerjoin(SpeakerCluster, Speaker.cluster_id == SpeakerCluster.id)
            .order_by(
                SpeakerCluster.member_count.desc().nullslast(),
                Speaker.confidence.asc().nullslast(),
                Speaker.created_at.desc(),
            )
        )

        total = query.count()
        pages = max(1, math.ceil(total / per_page))
        offset = (page - 1) * per_page
        speakers = query.offset(offset).limit(per_page).all()

        items = []
        for speaker in speakers:
            media_file = speaker.media_file
            cluster = speaker.cluster

            items.append(
                {
                    "speaker_uuid": str(speaker.uuid),
                    "speaker_name": speaker.name,
                    "display_name": speaker.display_name,
                    "suggested_name": speaker.suggested_name,
                    "suggestion_source": speaker.suggestion_source,
                    "confidence": float(speaker.confidence) if speaker.confidence else None,
                    "media_file_uuid": str(media_file.uuid) if media_file else None,
                    "media_file_title": (
                        media_file.title or media_file.filename if media_file else None
                    ),
                    "media_file_duration": float(media_file.duration)
                    if media_file and media_file.duration
                    else None,
                    "cluster_uuid": str(cluster.uuid) if cluster else None,
                    "cluster_label": cluster.label if cluster else None,
                    "cluster_member_count": int(cluster.member_count) if cluster else 0,
                    "verified": False,
                    "predicted_gender": speaker.predicted_gender,
                    "predicted_age_range": speaker.predicted_age_range,
                    "created_at": speaker.created_at.isoformat() if speaker.created_at else None,
                }
            )

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }

    def batch_verify_speakers(
        self,
        speaker_uuids: list[str],
        user_id: int,
        action: str = "accept",
        profile_uuid: str | None = None,
        display_name: str | None = None,
    ) -> dict[str, Any]:
        """Batch verify/name multiple speakers.

        Args:
            speaker_uuids: List of speaker UUIDs to verify.
            user_id: Owner user ID.
            action: "accept" (apply suggestion), "assign" (assign to profile), "name" (set display_name), "skip" (mark as reviewed/skipped).
            profile_uuid: Profile UUID (for "assign" action).
            display_name: Display name (for "name" action).

        Returns:
            Summary dict with updated_count, failed_count, errors.
        """
        updated = 0
        failed = 0
        errors: list[str] = []

        profile = None
        if action == "assign" and profile_uuid:
            profile = (
                self.db.query(SpeakerProfile)
                .filter(SpeakerProfile.uuid == profile_uuid, SpeakerProfile.user_id == user_id)
                .first()
            )
            if not profile:
                return {
                    "updated_count": 0,
                    "failed_count": len(speaker_uuids),
                    "errors": ["Profile not found"],
                }

        # Batch-fetch all speakers to avoid per-UUID queries
        speakers_by_uuid = {
            str(s.uuid): s
            for s in self.db.query(Speaker)
            .filter(Speaker.uuid.in_([str(u) for u in speaker_uuids]))
            .all()
        }

        for suuid in speaker_uuids:
            try:
                speaker = speakers_by_uuid.get(str(suuid))
                if not speaker or int(speaker.user_id) != user_id:
                    errors.append(f"Speaker {suuid} not found")
                    failed += 1
                    continue

                if action == "accept":
                    if speaker.suggested_name:
                        speaker.display_name = speaker.suggested_name  # type: ignore[assignment]
                        speaker.verified = True  # type: ignore[assignment]
                        updated += 1
                    else:
                        errors.append(f"Speaker {suuid} has no suggestion to accept")
                        failed += 1

                elif action == "assign" and profile:
                    speaker.profile_id = profile.id  # type: ignore[assignment]
                    speaker.display_name = profile.name  # type: ignore[assignment]
                    speaker.verified = True  # type: ignore[assignment]
                    updated += 1

                elif action == "name" and display_name:
                    speaker.display_name = display_name  # type: ignore[assignment]
                    speaker.verified = True  # type: ignore[assignment]
                    updated += 1

                elif action == "skip":
                    # Mark as verified (reviewed) so it doesn't reappear in inbox
                    speaker.verified = True  # type: ignore[assignment]
                    speaker.suggestion_source = "user_skipped"  # type: ignore[assignment]
                    updated += 1

                else:
                    errors.append(f"Invalid action '{action}' or missing parameters")
                    failed += 1

            except Exception as e:
                errors.append(f"Error processing speaker {suuid}: {e}")
                failed += 1

        try:
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            return {"updated_count": 0, "failed_count": len(speaker_uuids), "errors": [str(e)]}

        return {"updated_count": updated, "failed_count": failed, "errors": errors}

    # ------------------------------------------------------------------
    # Cluster listing / detail
    # ------------------------------------------------------------------

    def list_clusters(
        self,
        user_id: int,
        page: int = 1,
        per_page: int = 20,
        has_label: bool | None = None,
        search: str | None = None,
    ) -> dict[str, Any]:
        """List clusters with pagination and filtering.

        Args:
            user_id: Owner user ID.
            page: Page number (1-based).
            per_page: Items per page.
            has_label: Filter by whether cluster has a label.
            search: Search in cluster labels.

        Returns:
            Dict with items, total, page, per_page, pages.
        """
        query = (
            self.db.query(SpeakerCluster)
            .options(
                subqueryload(SpeakerCluster.promoted_to_profile),
            )
            .filter(SpeakerCluster.user_id == user_id)
        )

        if has_label is True:
            query = query.filter(SpeakerCluster.label.isnot(None))
        elif has_label is False:
            query = query.filter(SpeakerCluster.label.is_(None))

        if search:
            safe_search = search.replace("%", r"\%").replace("_", r"\_")
            query = query.filter(SpeakerCluster.label.ilike(f"%{safe_search}%", escape="\\"))

        label_priority = case(
            (SpeakerCluster.label.isnot(None), 0),
            (SpeakerCluster.promoted_to_profile_id.isnot(None), 0),
            else_=1,
        )
        query = query.order_by(
            label_priority,
            SpeakerCluster.member_count.desc(),
            SpeakerCluster.quality_score.desc().nullslast(),
            SpeakerCluster.created_at.desc(),
        )

        total = query.count()

        # Counts for section headers (unfiltered by search/has_label)
        base_count_query = self.db.query(SpeakerCluster).filter(SpeakerCluster.user_id == user_id)
        labeled_count = base_count_query.filter(
            (SpeakerCluster.label.isnot(None)) | (SpeakerCluster.promoted_to_profile_id.isnot(None))
        ).count()
        unlabeled_count = base_count_query.filter(
            SpeakerCluster.label.is_(None),
            SpeakerCluster.promoted_to_profile_id.is_(None),
        ).count()
        pages = max(1, math.ceil(total / per_page))
        offset = (page - 1) * per_page
        clusters = query.offset(offset).limit(per_page).all()

        # Batch-query gender composition for this page's clusters
        cluster_ids = [int(c.id) for c in clusters]
        gender_by_cluster: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        if cluster_ids:
            from sqlalchemy import func as sa_func

            gender_rows = (
                self.db.query(
                    SpeakerClusterMember.cluster_id,
                    Speaker.predicted_gender,
                    sa_func.count().label("cnt"),
                )
                .join(Speaker, SpeakerClusterMember.speaker_id == Speaker.id)
                .filter(SpeakerClusterMember.cluster_id.in_(cluster_ids))
                .group_by(SpeakerClusterMember.cluster_id, Speaker.predicted_gender)
                .all()
            )
            for row in gender_rows:
                gender_key = row[1] if row[1] else "__unknown__"
                gender_by_cluster[int(row[0])][gender_key] = int(row[2])

        items = []
        for cluster in clusters:
            promoted_profile = cluster.promoted_to_profile

            # Generate avatar URL for promoted profiles
            promoted_avatar_url = None
            if promoted_profile and promoted_profile.avatar_path:
                try:
                    from app.services.minio_service import get_file_url

                    promoted_avatar_url = get_file_url(promoted_profile.avatar_path, expires=3600)
                except Exception as e:
                    logger.debug("Failed to get avatar URL for profile: %s", e)

            # Build gender composition from batch query
            cid = int(cluster.id)
            gc = gender_by_cluster.get(cid, {})
            gc_members = []
            for g_key, cnt in gc.items():
                gender_val = None if g_key == "__unknown__" else g_key
                gc_members.extend([{"predicted_gender": gender_val}] * cnt)
            gender_composition = self._compute_gender_composition(gc_members)

            items.append(
                {
                    "uuid": str(cluster.uuid),
                    "label": cluster.label,
                    "description": cluster.description,
                    "user_id": int(cluster.user_id),
                    "member_count": int(cluster.member_count),
                    "promoted_to_profile_id": cluster.promoted_to_profile_id,
                    "promoted_to_profile_uuid": str(promoted_profile.uuid)
                    if promoted_profile
                    else None,
                    "promoted_to_profile_name": promoted_profile.name if promoted_profile else None,
                    "promoted_to_profile_avatar_url": promoted_avatar_url,
                    "quality_score": float(cluster.quality_score)
                    if cluster.quality_score is not None
                    else None,
                    "min_similarity": float(cluster.min_similarity)
                    if cluster.min_similarity is not None
                    else None,
                    "separation_score": float(cluster.separation_score)
                    if cluster.separation_score is not None
                    else None,
                    "gender_composition": gender_composition,
                    "created_at": cluster.created_at,
                    "updated_at": cluster.updated_at,
                }
            )

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
            "labeled_count": labeled_count,
            "unlabeled_count": unlabeled_count,
        }

    def get_cluster_detail(
        self,
        cluster_uuid: str,
        user_id: int,
    ) -> dict[str, Any] | None:
        """Get cluster detail with all members.

        Args:
            cluster_uuid: Cluster UUID.
            user_id: Owner user ID.

        Returns:
            Cluster detail dict, or None if not found.
        """
        cluster = (
            self.db.query(SpeakerCluster)
            .options(
                joinedload(SpeakerCluster.members)
                .joinedload(SpeakerClusterMember.speaker)
                .joinedload(Speaker.media_file),
                joinedload(SpeakerCluster.promoted_to_profile),
            )
            .filter(SpeakerCluster.uuid == cluster_uuid, SpeakerCluster.user_id == user_id)
            .first()
        )
        if not cluster:
            return None

        members = cluster.members

        # Check which members have transcript segments (= playable
        # via source media URL + seek to segment timestamps).
        member_speaker_ids = [int(m.speaker.id) for m in members if m.speaker]
        members_with_segments: set[int] = set()
        if member_speaker_ids:
            from sqlalchemy import func as sa_func

            seg_rows = (
                self.db.query(TranscriptSegment.speaker_id)
                .filter(TranscriptSegment.speaker_id.in_(member_speaker_ids))
                .group_by(TranscriptSegment.speaker_id)
                .having(sa_func.count() > 0)
                .all()
            )
            members_with_segments = {int(r[0]) for r in seg_rows}

        member_items = []
        for m in members:
            speaker = m.speaker
            if not speaker:
                continue

            media_file = speaker.media_file

            gender_conf = (
                speaker.attribute_confidence.get("gender") if speaker.attribute_confidence else None
            )

            member_items.append(
                {
                    "uuid": str(m.uuid),
                    "speaker_uuid": str(speaker.uuid),
                    "speaker_name": speaker.name,
                    "display_name": speaker.display_name,
                    "suggested_name": speaker.suggested_name,
                    "media_file_uuid": str(media_file.uuid) if media_file else None,
                    "media_file_title": (
                        media_file.title or media_file.filename if media_file else None
                    ),
                    "confidence": float(m.confidence),
                    "margin": float(m.margin) if m.margin is not None else None,
                    "verified": bool(speaker.verified),
                    "predicted_gender": speaker.predicted_gender,
                    "predicted_age_range": speaker.predicted_age_range,
                    "gender_confidence": float(gender_conf) if gender_conf is not None else None,
                    "gender_confirmed_by_user": bool(speaker.gender_confirmed_by_user),
                    "has_audio_clip": int(speaker.id) in members_with_segments,
                    "created_at": m.created_at,
                }
            )

        gender_composition = self._compute_gender_composition(member_items)
        promoted_profile = cluster.promoted_to_profile

        return {
            "uuid": str(cluster.uuid),
            "label": cluster.label,
            "description": cluster.description,
            "user_id": int(cluster.user_id),
            "member_count": int(cluster.member_count),
            "promoted_to_profile_id": cluster.promoted_to_profile_id,
            "promoted_to_profile_uuid": str(promoted_profile.uuid) if promoted_profile else None,
            "promoted_to_profile_name": promoted_profile.name if promoted_profile else None,
            "quality_score": float(cluster.quality_score)
            if cluster.quality_score is not None
            else None,
            "min_similarity": float(cluster.min_similarity)
            if cluster.min_similarity is not None
            else None,
            "separation_score": float(cluster.separation_score)
            if cluster.separation_score is not None
            else None,
            "gender_composition": gender_composition,
            "created_at": cluster.created_at,
            "updated_at": cluster.updated_at,
            "members": member_items,
        }

    @staticmethod
    def _compute_gender_composition(member_items: list[dict]) -> dict:
        """Compute gender composition summary for a list of cluster members."""
        male = sum(1 for m in member_items if m.get("predicted_gender") == "male")
        female = sum(1 for m in member_items if m.get("predicted_gender") == "female")
        total_g = male + female
        unknown = len(member_items) - total_g
        if total_g == 0:
            return {
                "male_count": 0,
                "female_count": 0,
                "unknown_count": unknown,
                "total_with_gender": 0,
                "dominant_gender": None,
                "gender_coherence": None,
                "gender_label": None,
                "has_gender_conflict": False,
            }
        dominant = "male" if male >= female else "female"
        dominant_count = max(male, female)
        coherence = dominant_count / total_g
        conflict = min(male, female) > 0
        if coherence == 1.0:
            label = f"100% {dominant.title()}"
        else:
            label = f"{dominant_count}/{total_g} {dominant.title()}"
        return {
            "male_count": male,
            "female_count": female,
            "unknown_count": unknown,
            "total_with_gender": total_g,
            "dominant_gender": dominant,
            "gender_coherence": round(coherence, 3),
            "gender_label": label,
            "has_gender_conflict": conflict,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_speaker_to_cluster(
        self,
        speaker: Speaker,
        cluster: SpeakerCluster,
        confidence: float,
        margin: float | None = None,
    ) -> None:
        """Add a speaker to a cluster (creates membership record).

        Args:
            speaker: Speaker to add.
            cluster: Target cluster.
            confidence: Cosine similarity to cluster centroid.
            margin: Difference between best and second-best match similarity.
        """
        existing = (
            self.db.query(SpeakerClusterMember)
            .filter(
                SpeakerClusterMember.cluster_id == cluster.id,
                SpeakerClusterMember.speaker_id == speaker.id,
            )
            .first()
        )
        if existing:
            return

        # Remove memberships in other clusters (speaker can only be in one)
        self.db.query(SpeakerClusterMember).filter(
            SpeakerClusterMember.speaker_id == speaker.id,
            SpeakerClusterMember.cluster_id != cluster.id,
        ).delete()

        member = SpeakerClusterMember(
            uuid=uuid4(),
            cluster_id=cluster.id,
            speaker_id=speaker.id,
            confidence=confidence,
            margin=margin,
        )
        self.db.add(member)
        speaker.cluster_id = cluster.id  # type: ignore[assignment]

        self.db.flush()
        cluster.member_count = (  # type: ignore[assignment]
            self.db.query(SpeakerClusterMember)
            .filter(SpeakerClusterMember.cluster_id == cluster.id)
            .count()
        )

    def _bulk_add_speakers_to_cluster(
        self,
        speakers: list[Speaker],
        cluster: SpeakerCluster,
        confidence: float | dict[int, float] = 0.0,
    ) -> int:
        """Add multiple speakers to a cluster in a single flush.

        Filters out speakers already in the cluster before adding.

        Args:
            confidence: Either a single float applied to all members,
                or a dict mapping speaker.id -> confidence for
                per-member values.

        Returns:
            Number of speakers added.
        """
        per_member = isinstance(confidence, dict)

        # Filter out speakers already in this cluster
        existing_speaker_ids = {
            int(r.speaker_id)
            for r in self.db.query(SpeakerClusterMember.speaker_id)
            .filter(SpeakerClusterMember.cluster_id == cluster.id)
            .all()
        }
        speakers = [s for s in speakers if int(s.id) not in existing_speaker_ids]

        count = 0
        for speaker in speakers:
            conf = confidence.get(int(speaker.id), 0.0) if per_member else confidence  # type: ignore[union-attr]
            member = SpeakerClusterMember(
                uuid=uuid4(),
                cluster_id=cluster.id,
                speaker_id=speaker.id,
                confidence=conf,
            )
            self.db.add(member)
            speaker.cluster_id = cluster.id  # type: ignore[assignment]
            count += 1

        self.db.flush()
        cluster.member_count = (  # type: ignore[assignment]
            self.db.query(SpeakerClusterMember)
            .filter(SpeakerClusterMember.cluster_id == cluster.id)
            .count()
        )
        return count

    def _create_singleton_cluster(
        self,
        speaker: Speaker,
        user_id: int,
        embedding: list[float],
    ) -> SpeakerCluster:
        """Create a new cluster with one speaker."""
        cluster = SpeakerCluster(
            uuid=uuid4(),
            user_id=user_id,
            member_count=1,
            quality_score=1.0,
            min_similarity=1.0,
        )
        self.db.add(cluster)
        self.db.flush()

        member = SpeakerClusterMember(
            uuid=uuid4(),
            cluster_id=cluster.id,
            speaker_id=speaker.id,
            confidence=1.0,
        )
        self.db.add(member)
        speaker.cluster_id = cluster.id  # type: ignore[assignment]
        self.db.flush()

        # Validate embedding is not a zero or NaN vector
        emb_norm = sum(x * x for x in embedding) ** 0.5
        if emb_norm < 0.01 or math.isnan(emb_norm):
            logger.warning(
                "Zero-vector embedding for speaker %s — skipping centroid storage",
                speaker.uuid,
            )
            return cluster

        # Store centroid in OpenSearch
        try:
            from app.services.opensearch_service import store_cluster_embedding

            store_cluster_embedding(
                cluster_uuid=str(cluster.uuid),
                user_id=user_id,
                embedding=embedding,
            )
        except Exception as e:
            logger.warning("Could not store cluster centroid in OpenSearch: %s", e)

        return cluster

    def _update_cluster_centroid(
        self,
        cluster: SpeakerCluster,
        user_id: int,
        refresh: str | bool = "wait_for",
    ) -> None:
        """Recalculate and store the cluster centroid embedding."""
        members = (
            self.db.query(SpeakerClusterMember)
            .options(joinedload(SpeakerClusterMember.speaker))
            .filter(SpeakerClusterMember.cluster_id == cluster.id)
            .all()
        )

        embeddings: list[list[float]] = []
        valid_members: list = []
        best_quality = -1.0
        best_speaker_id = None

        for m in members:
            speaker = m.speaker
            if not speaker:
                continue

            emb = self._get_speaker_embedding(speaker)
            if emb is not None:
                embeddings.append(emb)
                valid_members.append(m)
                quality = float(m.confidence) if m.confidence else 0.0
                if quality > best_quality:
                    best_quality = quality
                    best_speaker_id = int(speaker.id)

        if not embeddings:
            return

        # Weighted mean centroid: verified/profile-linked speakers get 2x weight
        arr = np.array(embeddings, dtype=np.float32)
        weights = np.array(
            [2.0 if m.speaker and m.speaker.profile_id else 1.0 for m in valid_members],
            dtype=np.float32,
        )
        centroid = np.average(arr, axis=0, weights=weights)
        norm = np.linalg.norm(centroid)
        if norm > 1e-8:
            centroid = centroid / norm
        else:
            logger.warning(
                "Zero-vector centroid for cluster %s — skipping OpenSearch storage",
                cluster.uuid,
            )
            return

        # Quality score: average centroid similarity (consistent with
        # per-member confidence shown in the UI).
        # min_similarity: tightest pairwise cosine similarity.
        if len(embeddings) >= 2:
            normed = arr / np.linalg.norm(arr, axis=1, keepdims=True).clip(1e-8)
            cluster.quality_score = float(np.mean(normed @ centroid))  # type: ignore[assignment]
            sim_matrix = normed @ normed.T
            iu = np.triu_indices(len(embeddings), k=1)
            cluster.min_similarity = float(np.min(sim_matrix[iu]))  # type: ignore[assignment]
        else:
            cluster.quality_score = 1.0  # type: ignore[assignment]
            cluster.min_similarity = 1.0  # type: ignore[assignment]

        if best_speaker_id:
            cluster.representative_speaker_id = best_speaker_id  # type: ignore[assignment]

        # Store in OpenSearch
        try:
            from app.services.opensearch_service import store_cluster_embedding

            store_cluster_embedding(
                cluster_uuid=str(cluster.uuid),
                user_id=user_id,
                embedding=centroid.tolist(),
                label=cluster.label,
                refresh=refresh,
            )
        except Exception as e:
            logger.warning("Could not update cluster centroid in OpenSearch: %s", e)

    def _get_speaker_embedding(self, speaker: Speaker) -> list[float] | None:
        """Get embedding for a speaker from the active index."""
        try:
            from app.services.opensearch_service import get_speaker_embedding

            return get_speaker_embedding(str(speaker.uuid))
        except Exception as e:
            logger.warning("Could not get embedding for speaker %s: %s", speaker.uuid, e)
            return None

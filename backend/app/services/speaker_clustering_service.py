"""
Speaker Clustering Service for pre-clustering unnamed speakers across files.

Uses a hybrid approach:
- Real-time: kNN against cluster centroids in OpenSearch + Union-Find assignment
- Batch: Build similarity graph via msearch, then connected-components or HDBSCAN

Cluster centroids are stored in OpenSearch with document_type="cluster".
"""

import logging
import math
from collections import defaultdict
from typing import Any
from uuid import uuid4

import numpy as np
from sqlalchemy.orm import Session

from app.models.media import Speaker
from app.models.media import SpeakerAudioClip
from app.models.media import SpeakerCluster
from app.models.media import SpeakerClusterMember
from app.models.media import SpeakerMatch
from app.models.media import SpeakerProfile

logger = logging.getLogger(__name__)

# Clustering thresholds
CLUSTER_ASSIGNMENT_THRESHOLD = 0.65  # Minimum similarity to join a cluster
CLUSTER_MERGE_THRESHOLD = 0.75  # Minimum similarity to auto-merge clusters


class UnionFind:
    """Disjoint-set data structure for connected-components clustering."""

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}
        self.rank: dict[int, int] = {}

    def find(self, x: int) -> int:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x: int, y: int) -> None:
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1

    def groups(self) -> dict[int, list[int]]:
        """Return mapping of root -> list of members."""
        result: dict[int, list[int]] = defaultdict(list)
        for x in self.parent:
            result[self.find(x)].append(x)
        return dict(result)


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
            speaker = self.db.query(Speaker).filter(Speaker.id == speaker_id).first()
            if not speaker:
                logger.warning(f"Speaker {speaker_id} not found")
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
                    self._add_speaker_to_cluster(speaker, cluster, best["similarity"])
                    self._update_cluster_centroid(cluster, user_id)
                    return cluster  # type: ignore[no-any-return]

            # No match — create a new singleton cluster
            cluster = self._create_singleton_cluster(speaker, user_id, embedding)
            return cluster  # type: ignore[no-any-return]

        except Exception as e:
            logger.error(f"Error in find_or_create_cluster for speaker {speaker_id}: {e}")
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
            logger.info(f"No speakers found for media file {media_file_id}")
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

    def build_clusters_from_matches(self, user_id: int) -> int:
        """Build clusters using connected-components on the SpeakerMatch table.

        This uses the existing cross-file match records to discover speaker groups
        without requiring OpenSearch.

        Args:
            user_id: Owner user ID.

        Returns:
            Number of clusters created or updated.
        """
        try:
            # Get all speaker matches for this user
            matches = (
                self.db.query(SpeakerMatch)
                .join(Speaker, SpeakerMatch.speaker1_id == Speaker.id)
                .filter(Speaker.user_id == user_id)
                .all()
            )

            if not matches:
                logger.info(f"No speaker matches found for user {user_id}")
                return 0

            # Build connected components using Union-Find
            uf = UnionFind()
            for match in matches:
                if float(match.confidence) >= CLUSTER_ASSIGNMENT_THRESHOLD:
                    uf.union(int(match.speaker1_id), int(match.speaker2_id))

            groups = uf.groups()
            cluster_count = 0

            for _root, member_ids in groups.items():
                if len(member_ids) < 2:
                    continue  # Skip singletons from match table

                # Check if any member already has a cluster
                existing_cluster = None
                for sid in member_ids:
                    speaker = self.db.query(Speaker).filter(Speaker.id == sid).first()
                    if speaker and speaker.cluster_id:
                        existing_cluster = (
                            self.db.query(SpeakerCluster)
                            .filter(SpeakerCluster.id == speaker.cluster_id)
                            .first()
                        )
                        if existing_cluster:
                            break

                if not existing_cluster:
                    existing_cluster = SpeakerCluster(
                        uuid=uuid4(),
                        user_id=user_id,
                        member_count=0,
                    )
                    self.db.add(existing_cluster)
                    self.db.flush()

                # Add all members
                for sid in member_ids:
                    speaker = self.db.query(Speaker).filter(Speaker.id == sid).first()
                    if not speaker:
                        continue

                    existing_member = (
                        self.db.query(SpeakerClusterMember)
                        .filter(
                            SpeakerClusterMember.cluster_id == existing_cluster.id,
                            SpeakerClusterMember.speaker_id == sid,
                        )
                        .first()
                    )
                    if not existing_member:
                        self._add_speaker_to_cluster(speaker, existing_cluster, 0.0)

                # Update centroid
                self._update_cluster_centroid(existing_cluster, user_id)
                cluster_count += 1

            self.db.commit()
            logger.info(f"Built {cluster_count} clusters from speaker matches for user {user_id}")
            return cluster_count

        except Exception as e:
            logger.error(f"Error building clusters from matches: {e}")
            self.db.rollback()
            return 0

    def batch_recluster(
        self,
        user_id: int,
        threshold: float = CLUSTER_ASSIGNMENT_THRESHOLD,
    ) -> dict[str, Any]:
        """Full re-clustering using similarity graph + connected-components.

        Fetches all speaker embeddings from OpenSearch, builds a similarity graph
        via batch kNN queries, and discovers clusters using connected-components.

        Args:
            user_id: Owner user ID.
            threshold: Cosine similarity threshold for edge creation.

        Returns:
            Summary dict with cluster counts and stats.
        """
        try:
            from app.services.opensearch_service import get_all_speaker_embeddings
            from app.services.opensearch_service import msearch_speaker_similarities

            # Step 1: Fetch all speaker embeddings
            speaker_data = get_all_speaker_embeddings(user_id)
            if not speaker_data:
                return {"status": "no_data", "clusters_created": 0}

            logger.info(f"Re-clustering {len(speaker_data)} speakers for user {user_id}")

            # Step 2: Build similarity graph via batch kNN
            similarities = msearch_speaker_similarities(speaker_data, user_id, k=10)

            # Step 3: Connected-components via Union-Find
            uuid_to_id: dict[str, int] = {}
            for sd in speaker_data:
                speaker = self.db.query(Speaker).filter(Speaker.uuid == sd["speaker_uuid"]).first()
                if speaker:
                    uuid_to_id[sd["speaker_uuid"]] = int(speaker.id)

            uf = UnionFind()
            for i, result_list in enumerate(similarities):
                src_uuid = speaker_data[i]["speaker_uuid"]
                src_id = uuid_to_id.get(src_uuid)
                if src_id is None:
                    continue
                uf.find(src_id)  # Ensure node exists

                for match in result_list:
                    if match["similarity"] < threshold:
                        continue
                    tgt_uuid = match.get("speaker_uuid")
                    tgt_id = uuid_to_id.get(tgt_uuid) if tgt_uuid else None
                    if tgt_id is not None and tgt_id != src_id:
                        uf.union(src_id, tgt_id)

            # Step 4: Clear existing non-promoted clusters
            old_clusters = (
                self.db.query(SpeakerCluster)
                .filter(
                    SpeakerCluster.user_id == user_id,
                    SpeakerCluster.promoted_to_profile_id.is_(None),
                )
                .all()
            )
            for oc in old_clusters:
                # Clear speaker cluster_id references
                self.db.query(Speaker).filter(Speaker.cluster_id == oc.id).update(
                    {"cluster_id": None}
                )
                self.db.delete(oc)
            self.db.flush()

            # Step 5: Create new clusters from groups
            groups = uf.groups()
            clusters_created = 0
            speakers_assigned = 0

            for _root, member_ids in groups.items():
                if len(member_ids) < 2:
                    continue

                cluster = SpeakerCluster(
                    uuid=uuid4(),
                    user_id=user_id,
                    member_count=0,
                )
                self.db.add(cluster)
                self.db.flush()

                for sid in member_ids:
                    speaker = self.db.query(Speaker).filter(Speaker.id == sid).first()
                    if speaker:
                        self._add_speaker_to_cluster(speaker, cluster, 0.0)
                        speakers_assigned += 1

                self._update_cluster_centroid(cluster, user_id)
                clusters_created += 1

            self.db.commit()
            logger.info(
                f"Re-clustering complete: {clusters_created} clusters, "
                f"{speakers_assigned} speakers assigned"
            )

            return {
                "status": "completed",
                "total_speakers": len(speaker_data),
                "clusters_created": clusters_created,
                "speakers_assigned": speakers_assigned,
                "singletons": len(speaker_data) - speakers_assigned,
            }

        except Exception as e:
            logger.error(f"Error in batch re-clustering: {e}")
            self.db.rollback()
            return {"status": "error", "message": str(e)}

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
                    f"Cluster not found for merge: source={source_uuid}, target={target_uuid}"
                )
                return None

            # Move members
            members = (
                self.db.query(SpeakerClusterMember)
                .filter(SpeakerClusterMember.cluster_id == source.id)
                .all()
            )
            for member in members:
                # Check for duplicate
                existing = (
                    self.db.query(SpeakerClusterMember)
                    .filter(
                        SpeakerClusterMember.cluster_id == target.id,
                        SpeakerClusterMember.speaker_id == member.speaker_id,
                    )
                    .first()
                )
                if existing:
                    self.db.delete(member)
                else:
                    member.cluster_id = target.id  # type: ignore[assignment]

                # Update speaker FK
                speaker = self.db.query(Speaker).filter(Speaker.id == member.speaker_id).first()
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
                logger.warning(f"Could not delete source cluster embedding: {e}")

            self.db.delete(source)
            self._update_cluster_centroid(target, user_id)
            self.db.commit()

            logger.info(f"Merged cluster {source_uuid} into {target_uuid}")
            return target  # type: ignore[no-any-return]

        except Exception as e:
            logger.error(f"Error merging clusters: {e}")
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
                .first()
            )
            if not source:
                logger.warning(f"Cluster {cluster_uuid} not found")
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

            # Delete source if empty
            if source.member_count == 0:
                try:
                    from app.services.opensearch_service import delete_cluster_embedding

                    delete_cluster_embedding(str(source.uuid))
                except Exception:
                    logger.debug("Failed to remove cluster embedding from OpenSearch")
                self.db.delete(source)

            self.db.commit()
            logger.info(f"Split {len(speakers_to_move)} speakers from cluster {cluster_uuid}")
            return new_cluster

        except Exception as e:
            logger.error(f"Error splitting cluster: {e}")
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
                logger.warning(f"Cluster {cluster_uuid} not found")
                return None

            if cluster.promoted_to_profile_id:
                existing = (
                    self.db.query(SpeakerProfile)
                    .filter(SpeakerProfile.id == cluster.promoted_to_profile_id)
                    .first()
                )
                if existing:
                    logger.info(
                        f"Cluster {cluster_uuid} already promoted to profile {existing.uuid}"
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

            # Link cluster
            cluster.promoted_to_profile_id = profile.id  # type: ignore[assignment]

            # Assign all member speakers to the profile
            members = (
                self.db.query(SpeakerClusterMember)
                .filter(SpeakerClusterMember.cluster_id == cluster.id)
                .all()
            )
            for member in members:
                speaker = self.db.query(Speaker).filter(Speaker.id == member.speaker_id).first()
                if speaker:
                    speaker.profile_id = profile.id  # type: ignore[assignment]
                    speaker.display_name = name  # type: ignore[assignment]
                    speaker.verified = True  # type: ignore[assignment]

            # Update profile embedding
            from app.services.profile_embedding_service import ProfileEmbeddingService

            self.db.commit()
            ProfileEmbeddingService.update_profile_embedding(self.db, int(profile.id))

            logger.info(
                f"Promoted cluster {cluster_uuid} to profile '{name}' ({len(members)} speakers)"
            )
            return profile

        except Exception as e:
            logger.error(f"Error promoting cluster to profile: {e}")
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
            .filter(
                Speaker.user_id == user_id,
                Speaker.verified.is_(False),
                Speaker.profile_id.is_(None),
            )
            .outerjoin(SpeakerCluster, Speaker.cluster_id == SpeakerCluster.id)
            .order_by(
                SpeakerCluster.member_count.desc().nullslast(),
                Speaker.confidence.desc().nullslast(),
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
            cluster = (
                self.db.query(SpeakerCluster)
                .filter(SpeakerCluster.id == speaker.cluster_id)
                .first()
                if speaker.cluster_id
                else None
            )
            audio_clip = (
                self.db.query(SpeakerAudioClip)
                .filter(SpeakerAudioClip.speaker_id == speaker.id)
                .order_by(SpeakerAudioClip.quality_score.desc())
                .first()
            )

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
                    "audio_clip_uuid": str(audio_clip.uuid) if audio_clip else None,
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
            action: "accept" (apply suggestion), "assign" (assign to profile), "name" (set display_name).
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

        for suuid in speaker_uuids:
            try:
                speaker = (
                    self.db.query(Speaker)
                    .filter(Speaker.uuid == suuid, Speaker.user_id == user_id)
                    .first()
                )
                if not speaker:
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
        query = self.db.query(SpeakerCluster).filter(SpeakerCluster.user_id == user_id)

        if has_label is True:
            query = query.filter(SpeakerCluster.label.isnot(None))
        elif has_label is False:
            query = query.filter(SpeakerCluster.label.is_(None))

        if search:
            query = query.filter(SpeakerCluster.label.ilike(f"%{search}%"))

        query = query.order_by(SpeakerCluster.member_count.desc(), SpeakerCluster.created_at.desc())

        total = query.count()
        pages = max(1, math.ceil(total / per_page))
        offset = (page - 1) * per_page
        clusters = query.offset(offset).limit(per_page).all()

        items = []
        for cluster in clusters:
            promoted_profile = None
            if cluster.promoted_to_profile_id:
                promoted_profile = (
                    self.db.query(SpeakerProfile)
                    .filter(SpeakerProfile.id == cluster.promoted_to_profile_id)
                    .first()
                )

            rep_clip = None
            if cluster.representative_speaker_id:
                rep_clip = (
                    self.db.query(SpeakerAudioClip)
                    .filter(
                        SpeakerAudioClip.speaker_id == cluster.representative_speaker_id,
                        SpeakerAudioClip.is_representative.is_(True),
                    )
                    .first()
                )

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
                    "quality_score": float(cluster.quality_score)
                    if cluster.quality_score
                    else None,
                    "representative_clip_uuid": str(rep_clip.uuid) if rep_clip else None,
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
            .filter(SpeakerCluster.uuid == cluster_uuid, SpeakerCluster.user_id == user_id)
            .first()
        )
        if not cluster:
            return None

        members = (
            self.db.query(SpeakerClusterMember)
            .filter(SpeakerClusterMember.cluster_id == cluster.id)
            .all()
        )

        member_items = []
        for m in members:
            speaker = self.db.query(Speaker).filter(Speaker.id == m.speaker_id).first()
            if not speaker:
                continue

            media_file = speaker.media_file
            audio_clip = (
                self.db.query(SpeakerAudioClip)
                .filter(SpeakerAudioClip.speaker_id == speaker.id)
                .order_by(SpeakerAudioClip.quality_score.desc())
                .first()
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
                    "verified": bool(speaker.verified),
                    "predicted_gender": speaker.predicted_gender,
                    "predicted_age_range": speaker.predicted_age_range,
                    "has_audio_clip": audio_clip is not None,
                    "created_at": m.created_at,
                }
            )

        promoted_profile = None
        if cluster.promoted_to_profile_id:
            promoted_profile = (
                self.db.query(SpeakerProfile)
                .filter(SpeakerProfile.id == cluster.promoted_to_profile_id)
                .first()
            )

        return {
            "uuid": str(cluster.uuid),
            "label": cluster.label,
            "description": cluster.description,
            "user_id": int(cluster.user_id),
            "member_count": int(cluster.member_count),
            "promoted_to_profile_id": cluster.promoted_to_profile_id,
            "promoted_to_profile_uuid": str(promoted_profile.uuid) if promoted_profile else None,
            "promoted_to_profile_name": promoted_profile.name if promoted_profile else None,
            "quality_score": float(cluster.quality_score) if cluster.quality_score else None,
            "created_at": cluster.created_at,
            "updated_at": cluster.updated_at,
            "members": member_items,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_speaker_to_cluster(
        self,
        speaker: Speaker,
        cluster: SpeakerCluster,
        confidence: float,
    ) -> None:
        """Add a speaker to a cluster (creates membership record)."""
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

        member = SpeakerClusterMember(
            uuid=uuid4(),
            cluster_id=cluster.id,
            speaker_id=speaker.id,
            confidence=confidence,
        )
        self.db.add(member)
        speaker.cluster_id = cluster.id  # type: ignore[assignment]

        cluster.member_count = (  # type: ignore[assignment]
            self.db.query(SpeakerClusterMember)
            .filter(SpeakerClusterMember.cluster_id == cluster.id)
            .count()
            + 1  # +1 for the one we just added (not yet flushed)
        )
        self.db.flush()

        # Re-count after flush to be accurate
        cluster.member_count = (  # type: ignore[assignment]
            self.db.query(SpeakerClusterMember)
            .filter(SpeakerClusterMember.cluster_id == cluster.id)
            .count()
        )

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

        # Store centroid in OpenSearch
        try:
            from app.services.opensearch_service import store_cluster_embedding

            store_cluster_embedding(
                cluster_uuid=str(cluster.uuid),
                user_id=user_id,
                embedding=embedding,
            )
        except Exception as e:
            logger.warning(f"Could not store cluster centroid in OpenSearch: {e}")

        return cluster

    def _update_cluster_centroid(
        self,
        cluster: SpeakerCluster,
        user_id: int,
    ) -> None:
        """Recalculate and store the cluster centroid embedding."""
        members = (
            self.db.query(SpeakerClusterMember)
            .filter(SpeakerClusterMember.cluster_id == cluster.id)
            .all()
        )

        embeddings: list[list[float]] = []
        best_quality = -1.0
        best_speaker_id = None

        for m in members:
            speaker = self.db.query(Speaker).filter(Speaker.id == m.speaker_id).first()
            if not speaker:
                continue

            emb = self._get_speaker_embedding(speaker)
            if emb is not None:
                embeddings.append(emb)
                # Track representative speaker (longest total speaking time heuristic)
                quality = float(m.confidence) if m.confidence else 0.0
                if quality > best_quality:
                    best_quality = quality
                    best_speaker_id = int(speaker.id)

        if not embeddings:
            return

        # L2-normalized average centroid
        arr = np.array(embeddings)
        centroid = np.mean(arr, axis=0)
        norm = np.linalg.norm(centroid)
        if norm > 1e-8:
            centroid = centroid / norm

        # Calculate quality score (average pairwise similarity within cluster)
        if len(embeddings) >= 2:
            similarities = []
            for i in range(len(embeddings)):
                for j in range(i + 1, len(embeddings)):
                    sim = float(np.dot(embeddings[i], embeddings[j]))
                    similarities.append(sim)
            cluster.quality_score = sum(similarities) / len(similarities)  # type: ignore[assignment]
        else:
            cluster.quality_score = 1.0  # type: ignore[assignment]

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
            )
        except Exception as e:
            logger.warning(f"Could not update cluster centroid in OpenSearch: {e}")

    def _get_speaker_embedding(self, speaker: Speaker) -> list[float] | None:
        """Get embedding for a speaker from OpenSearch."""
        try:
            from app.services.opensearch_service import get_speaker_embedding

            embedding = get_speaker_embedding(str(speaker.uuid))
            return embedding if embedding else None
        except Exception as e:
            logger.warning(f"Could not get embedding for speaker {speaker.uuid}: {e}")
            return None

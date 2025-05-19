# Project Plan: Full-Stack Transcription & Speaker Diarization Web Application

## 1. Functional and Non-Functional Requirements

**Functional Requirements:** The application will provide a rich set of features for audio/video transcription and speaker diarization:

* **Media Upload & Management:** Users can upload audio or video files (various formats) and see them listed in a media library. Each file entry can store filename, upload date/time, duration, and user-defined tags. Users can play back the media and manage it (rename, delete, add tags). Uploads are handled asynchronously to accommodate large files.
* **Automated Transcription with Diarization:** Upon upload, the system automatically generates a **transcript** for the media using WhisperX (a Whisper-based ASR with alignment). The transcript includes **speaker diarization**, distinguishing different speakers in the audio (“who spoke when”). The diarization uses a state-of-the-art open-source model (e.g. PyAnnote) to achieve high accuracy in speaker differentiation. The transcript is time-aligned so that each word or segment has a timestamp.
* **Speaker Identification Across Files:** The system leverages speaker embedding models (PyAnnote) to create a **voice fingerprint** for each speaker. When a new file is processed, the identified speakers’ embeddings are compared to previously stored embeddings to recognize if a speaker has been seen before. This enables **persistent speaker identities** across uploads – e.g. if “Alice” was identified in one file, future files with her voice can be labeled as Alice automatically. Users can edit speaker names (rename “Speaker 1” to a real name) and those names persist for that user’s future transcripts.
* **Playback with Transcript Highlighting:** Users can view each media file with an integrated player (using Plyr) and a scrollable transcript. As the media plays, the current spoken text in the transcript is highlighted in real-time (karaoke-style highlighting). Users can also click on the transcript to seek the media player to that point. This provides an interactive way to navigate the media via text.
* **Search and Filtering:** Powerful search capabilities are included to help users find information:

  * **Filename/Tag Search:** Users can search media by filename or by tags.
  * **Transcript Content Search:** Users can search within transcript contents (keywords). The system supports both keyword-based search and semantic search. It uses OpenSearch to combine traditional text matching with **vector-based semantic search**, so results can be fetched by exact terms or concept similarity.
  * **Speaker-based Search:** Users can filter or search media by speaker. For example, finding all files where “Alice” speaks, or even searching for a speaker by an example (using the speaker embeddings).
  * **Date/Time Filters:** A gallery view displays all uploaded media with a sidebar to filter by upload date range or media duration.
* **Comments & Annotations:** Users can add comments or annotations to a media file. Comments can be **time-stamped** (linked to a specific moment in the media) or general for the whole file. For time-stamped comments, clicking the comment will jump the player to that timestamp. This is useful for note-taking or review of meeting recordings, etc. All comments are visible in the file view (sorted by time if applicable).
* **Tags & Organization:** Users can tag media files with custom keywords (topics, project names, etc.). Tags are manageable per file and visible in the gallery. The filter sidebar allows filtering the library by tags for organization.
* **Editing Transcripts and Speakers:** The transcript text and speaker attributions can be manually edited in the UI. Users with appropriate permission can correct transcription errors or adjust punctuation, and these edits are saved persistently. They can also merge or split transcript segments if needed. Speaker labels can be reassigned – for example, if two speaker segments were incorrectly separated or a speaker was not automatically recognized, the user can manually label them. The system updates its records accordingly (and potentially the speaker embedding database if a merge occurs).
* **Summarization:** The application can generate a **summary** of the transcript content. It uses local Large Language Models (LLMs) to produce concise summaries of the conversation or speech. For longer transcripts, the text is broken into chunks and summarized in parts, then combined (iterative refinement) to ensure the entire content is covered. The summary is stored with the file and displayed in the UI (e.g. as a “Summary” section). The system supports using smaller (1B–3B parameter) local models for efficiency, with the option to plug in larger models if available. Summaries can be generated in the background after transcription.
* **Subtitle Export:** The user can export the transcript as subtitle files. One-click export to **SRT or VTT** (with speaker labels optionally included in the text). The system can also **embed subtitles into the video** itself using FFmpeg. For example, an MP4 video can be output with burned-in captions by invoking FFmpeg’s subtitle filter. This allows users to download the original video with English captions overlayed.
* **Notifications & Job Status:** Because transcription and other processing are done asynchronously, users are kept informed of progress. The app includes an in-app notification system: for example, a notification or status indicator when a transcription job finishes or if it fails. A “Jobs/Tasks Status” page (or dropdown) shows the list of background jobs (transcriptions, summaries, exports, etc.) with their current status (pending/running/completed). This might be represented by a bell icon in the UI that, when clicked, shows recent job statuses.
* **Authentication & Roles:** The application requires user login. It uses OAuth2 (JWT-based) auth for the API. Users have roles such as **Standard User** and **Admin**. Standard users can only see and manage their own files and data. Admins have access to an admin dashboard for managing the system (view all users, files, and system metrics). The admin dashboard might show aggregate stats (total number of files, total processing time used, etc.) and allow user management (e.g., promoting a user to admin, disabling accounts).
* **User Settings:** Each user has a settings/profile page. Users can manage their profile info (name, email, password), and set preferences such as default language for transcripts or whether to auto-run summaries on upload. They can also manage personal settings like notification preferences (e.g., enable/disable in-app notifications or email notifications if implemented later).
* **Multilingual Support:** The transcription engine supports multiple languages. If a media file’s language is not English, the system can still transcribe in the original language (Whisper models are multilingual). Additionally, the system can **translate transcripts to English** on demand. For example, after getting a Spanish transcript, the user can request an English translation of it (or the system can auto-provide one). Summaries are generally provided in English (the app can translate non-English content before summarizing if needed).
* **Analytics & Insights:** Beyond raw transcription, the app provides analytical insights:

  * **Speaker Talk Time:** A visualization (e.g. pie chart) for each recording showing how much each participant spoke (based on diarization timestamps). For instance, in a meeting recording, it can display that Speaker A spoke 60% of the time vs Speaker B 40%.
  * **Sentiment Analysis:** The system can run a sentiment analysis on segments or overall, giving a sense of the tone of the conversation (e.g. whether a speaker was mostly positive/neutral/negative). This could be summarized per speaker or per time interval.
  * **Keyword Extraction:** Key topics or keywords from the conversation are extracted (e.g. using NLP algorithms) and shown. This helps quickly understand main topics discussed. These keywords might also be used as suggested tags for the file.
  * These analytics are optional and run after transcription (possibly as part of the summarization task or a separate analysis task). They appear in the file’s detail view (e.g. an “Insights” section).
* **Scalability & Performance (Non-functional needs):** The system should handle reasonably large files (e.g. hour-long recordings) and multiple concurrent users. It uses background processing so the UI remains responsive. The architecture supports adding more workers or resources if usage grows (see scalability section). It should be **robust** – handle errors gracefully (e.g., audio file not supported, or model failure) by notifying the user and not crashing.
* **Security (Non-functional):** All user data is protected. JWT tokens secure API requests; password storage is hashed. File storage is private (accessible only through authorized requests). Role-based access ensures no data leakage between users. The web app will use HTTPS in production (behind NGINX with SSL) to encrypt data in transit. Rate limiting or other controls may be in place to prevent abuse of the API.
* **Usability (Non-functional):** The UI is designed to be intuitive and responsive. It should work on modern browsers and adapt to different screen sizes (desktop, tablet). Short paragraphs and clear typography in transcripts improve readability. Headings, lists, and other formatting in this technical plan (and analogously, clarity in the UI) are emphasized to enhance readability.

**Non-Functional Requirements Summary:** In addition to the above, the solution emphasizes maintainability and modern best practices. The codebase will be modular and well-documented to ease future enhancements. The system will store essential data reliably – user accounts, transcript text, speaker info, job statuses – in a durable database. It will log events and errors for monitoring. The overall design favors open-source components and on-premise deployment (for privacy and cost control), but it remains flexible to integrate external services if needed in the future.

## 2. Architecture and Component Design

**High-Level Architecture:** This application follows a modular **multi-tier architecture**, separating the front-end client, the back-end API, background workers, and storage components. The goal is to ensure each concern (UI, API logic, asynchronous processing, data storage, search) is loosely coupled and can be scaled or maintained independently. At a high level, the system consists of:

* **Client (Browser)** – A Svelte web application that runs in the user’s browser, providing the user interface and interacting with the back-end via HTTP(S) requests (and web sockets for live updates).

* **Backend API (FastAPI)** – A RESTful API server (Python FastAPI) that handles client requests for data and orchestrates actions. It serves JSON for data (e.g., transcripts, search results) and also serves the front-end static files in production. It enqueues heavy jobs to the worker queue and queries the database and search index.

* **Asynchronous Task Workers (Celery)** – One or more Celery worker processes that run intensive tasks in the background (transcription, speaker ID, summarization, etc.). They pull jobs from a message broker queue so that such tasks run outside the main API request thread, preventing blocking. *Using Celery allows heavy background computations to be offloaded to separate worker processes.* The workers have access to GPUs (if available) for ML tasks.

* **Data Storage** – This includes a **PostgreSQL database** for relational data (user accounts, file metadata, transcript text, comments, etc.) and an **object storage** (MinIO or S3) for storing the actual media files and large transcript files if needed. The database ensures data persistence and consistency, while MinIO/S3 is used for scalable storage of potentially large media blobs.

* **Search Engine (OpenSearch)** – An OpenSearch cluster (could be a single node to start) stores indexed transcript data and speaker embeddings. It provides fast full-text search and vector similarity search. The application uses OpenSearch’s **hybrid search** capabilities to combine keyword and semantic search results for queries. It also can perform efficient k-NN queries on speaker embedding vectors to identify matching speakers.

* **AI/ML Services** – This refers to the ML models integrated into the system:

  * **WhisperX** for speech-to-text with alignment and word-level timestamps.
  * **Pyannote (Diarization & Embeddings)** for speaker diarization and creating speaker embeddings (voice prints).
  * **Local LLM** for text summarization (and possibly translation) tasks.
  * **FFmpeg** for media processing (embedding subtitles in videos, converting formats if needed).
    These run as libraries within the Celery workers – there aren’t separate external AI servers, everything is self-contained in our service for privacy and control (unless configured to use external APIs optionally).

* **Message Broker** – Celery requires a message broker (Redis or RabbitMQ) to queue tasks. In our architecture we include a broker service (e.g., Redis) that the FastAPI API uses to send task messages and the Celery workers consume. The broker mediates communication between FastAPI (as the client adding tasks) and the workers.

* **Web Server / Reverse Proxy** – NGINX sits in front of the FastAPI UVicorn server. It serves static files (the compiled Svelte app and assets) and proxies API requests to FastAPI. It also can handle SSL termination and can be configured to forward WebSocket connections for notifications to FastAPI. NGINX helps in handling multiple client connections efficiently and serving the UI with compression and caching.

**Component Interactions:** When a user performs an action, multiple components interact in a sequence:

1. The user’s browser (Svelte app) sends a request to the FastAPI backend (for example, uploading a file or requesting search results). This goes through NGINX which routes it to FastAPI.
2. FastAPI handles the request. For a file upload, FastAPI will save file metadata in PostgreSQL and the file itself to MinIO storage, then **enqueue a transcription task** to Celery via the broker. It immediately responds to the client that the file is received and processing has started.
3. A Celery **worker** picks up the transcription task from the broker queue. It loads the audio from storage, runs the WhisperX transcription followed by Pyannote diarization (using GPU acceleration if available). The worker then saves the resulting transcript segments and speaker info to the database, and updates the search index (OpenSearch) with the new transcript text and any new speaker vectors. It may also enqueue subsequent tasks (e.g., a summarization task for that file) or do them inline as part of the workflow.
4. When the background task is complete, FastAPI (or a background callback) sends a notification to the user – e.g., via a WebSocket event or by updating a status that the front-end polls. The user sees in the UI that the transcript is ready. The transcript data can then be fetched via an API call (FastAPI reads from Postgres) and displayed.
5. For searching transcripts, the front-end calls a search API endpoint on FastAPI. FastAPI translates that request into an OpenSearch query (using full-text and vector search as appropriate) and returns matching files/segments to the front-end.
6. Any time the user plays a video or audio, the front-end uses the Plyr player. The transcript highlighting is achieved purely on the front-end by syncing the player’s current time with the transcript timestamps (no additional server calls needed during playback).

**Component Responsibilities:** Each component in the architecture has a clear responsibility, summarized below:

| **Component**                    | **Role & Responsibilities**                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Svelte Frontend (Browser UI)** | Provides a responsive UI for all features: login screen, file upload form, media gallery with filters, file detail view (player + transcript + comments + tags + summary), search bar/results, user settings, and admin dashboard. Communicates with backend via REST API calls (and opens a WebSocket for live notifications). Uses Plyr for media playback and manages transcript highlight sync.                                                                                                                                                                                                                                                                                                                            |
| **NGINX Reverse Proxy**          | Serves static files (the compiled Svelte app) and proxies API calls to the FastAPI backend. Terminates SSL in production. Handles routing `/api/*` to FastAPI and others to static content. Also configured to proxy WebSocket connections (for notifications) to FastAPI.                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **FastAPI Backend API**          | Implements the REST API endpoints for the application. Handles authentication (JWT token issuance on login), and all CRUD operations: uploading files, retrieving file lists, fetching transcripts, posting comments, editing text, etc. Orchestrates background work by enqueuing Celery tasks (for long-running jobs). Performs input validation, calls database queries, and aggregates data (e.g., combining transcript segments with speaker names) to send to frontend. Also triggers search queries to OpenSearch and returns results. Essentially the central coordinator between front-end and all back-end services.                                                                                                 |
| **Celery Workers**               | Perform heavy processing tasks asynchronously. They handle: **transcription & diarization** (invoking WhisperX and Pyannote models), **speaker embedding matching** (comparing embeddings to identify speakers), **LLM summarization** (loading the local model and generating summaries), **translation** tasks, **subtitle generation** (calling FFmpeg to burn subtitles), and any **analytics computation** (sentiment, keyword extraction). The workers are designed to keep models loaded in memory when possible for performance. Multiple Celery workers can run in parallel (scaled out in Docker or on multiple machines) to handle concurrent jobs.                                                                 |
| **Broker (Redis/RabbitMQ)**      | Message broker that queues tasks from FastAPI to Celery. FastAPI pushes a task message (e.g., “transcribe file X”) to the broker; a Celery worker listening on the queue retrieves it and executes it. The broker ensures decoupling – FastAPI doesn’t need to wait, and workers can be distributed. Redis is a simple in-memory broker option; RabbitMQ is another robust option (either can be used).                                                                                                                                                                                                                                                                                                                        |
| **PostgreSQL Database**          | Stores relational data: **Users** (accounts, roles, settings), **MediaFiles** (each uploaded file’s metadata), **TranscriptSegments** (text segments with start/end times and speaker references), **Speakers** (speaker profiles for identified voices), **Comments** (user comments on transcripts), **Tags** (and file-tag associations), **Notifications/Tasks** (if we log job status or notifications). Ensures data persistence and supports transactions (e.g., uploading a file and creating a transcription job entry can be atomic). This is the source of truth for user data and transcripts.                                                                                                                     |
| **MinIO/S3 Storage**             | Object storage for uploaded media files and large artifacts. When a user uploads a file, it’s streamed to this storage (MinIO in dev, which is S3-compatible, and in production it could be an actual AWS S3 bucket or any S3 service). The storage returns a URL or key for the file, which is saved in Postgres. Workers fetch the media content from here for processing. This decouples file storage from the application servers (important for scalability, since workers might be on different hosts).                                                                                                                                                                                                                  |
| **OpenSearch Cluster**           | Full-text and vector search engine. Maintains an **index of transcripts** (for example, each file’s transcript text and metadata is indexed, or possibly each segment for fine-grained search). Also maintains a **speaker embedding index** (each known speaker’s voice embedding vector, with an ID and name). On search queries, OpenSearch can perform keyword search with relevance scoring and vector similarity search for semantic matches, combining them for better results. It allows filtering by fields (e.g., file tags, speaker name, date) for the advanced filter UI.                                                                                                                                         |
| **AI Models (Libraries)**        | Not standalone services but crucial parts of the architecture running within the workers: **WhisperX** (speech recognition with alignment) provides high-accuracy transcripts with word timings. **Pyannote.audio** models provide diarization – they segment audio by speaker and also generate speaker **embeddings** that represent a speaker’s voice. **Local LLM (via vLLM or HF Transformers)** provides NLP capabilities for summarization (and could be used for sentiment or translation as well). **FFmpeg** is used for any audio/video format conversions (e.g., extracting audio from video for processing) and for overlaying subtitles on video outputs. These components are encapsulated in the worker layer. |

*Rationale:* This design ensures that user interactions (through FastAPI) are fast – any operation that could be slow is done asynchronously. The database ensures consistency (for example, once a transcript is generated and saved, any API call for that transcript will fetch the exact same data). The OpenSearch component is separate from Postgres to offload heavy search queries and to enable advanced search features without affecting the transactional workload of Postgres.

**Diagram Description:** (Refer to the architecture diagram above.) The client interacts with the **FastAPI** backend via HTTP(S). NGINX routes these requests appropriately. The **FastAPI** server handles quick operations and pushes long-running tasks to **Celery** through the **broker**. Celery workers then use **WhisperX** and **Pyannote** (dashed lines indicate interactions with ML models) to process audio and produce transcripts, saving results in **Postgres** and files in **MinIO**, and updating **OpenSearch** indexes. The front-end is notified and then fetches the results from FastAPI (which in turn reads from Postgres/OpenSearch). This separation of concerns improves scalability and maintainability.

**Design for Scale & Maintainability:** Each major part of the system (front-end, API, worker, data stores) can be scaled or replaced independently:

* We can run multiple FastAPI instances behind NGINX to handle more concurrent users (since it’s stateless and uses a shared DB).
* We can run multiple Celery workers or even dedicate certain workers to specific task types (e.g., GPU-intensive transcription vs CPU-bound summarization) using separate queues.
* The database and OpenSearch can be scaled vertically (bigger instance) or horizontally (read replicas, OpenSearch clustering).
* The use of JWT for auth means no sticky sessions are needed on the back-end, simplifying load balancing.
* If needed in the future, each functionality (transcription, search, summarization) could even be broken into a microservice with its own API. However, initially, we keep them within the same FastAPI/Celery context for simplicity and only one deployment.

The component design also facilitates **maintainability**: clear API boundaries and data models mean that developers can work on the front-end (Svelte) and back-end (FastAPI) somewhat independently. The integration points are the REST APIs and the database/search. By using standard protocols (HTTP, SQL, etc.), we reduce tight coupling. The code will be organized in a way that reflects these components (for example, separate FastAPI routers for file management, search, auth; separate modules for Celery tasks related to transcription, summarization, etc.).

## 3. Backend API Design (Endpoints and Payloads)

The FastAPI backend exposes a set of RESTful API endpoints under a common prefix (e.g., `/api`). These endpoints handle resources like **files**, **transcripts**, **speakers**, **comments**, and **search**. Below is an overview of key API endpoints and their request/response structures:

* **Authentication & User APIs:**

  * `POST /api/auth/register`: Create a new user account (if open registration is allowed; otherwise admins create users). Expects JSON with username, email, password. Returns success or error.
  * `POST /api/auth/login`: User login. Expects JSON with credentials; on success returns a JWT token (and maybe refresh token) that the client will use in Authorization header for subsequent calls.
  * `GET /api/auth/me`: Returns the current user’s profile information and settings. (Requires JWT auth.)
  * `PUT /api/auth/me`: Update profile or settings (e.g., change password, notification preferences).
  * (Admin only) `GET /api/admin/users`: List all users or get user stats. Admin JWT required.

* **File Upload & Management:**

  * `POST /api/files`: Upload a media file for transcription. This is a multipart/form-data request containing the file (and optional metadata like title or tags). The response returns a JSON with the new file’s ID and a status (e.g., “processing”). For example:

    ```json
    {
      "file_id": 123,
      "filename": "meeting.mp4",
      "status": "processing",
      "upload_time": "2025-05-04T17:30:00Z"
    }
    ```

    The server at this point has queued the transcription job.
  * `GET /api/files`: List files the user has uploaded. Supports query params for filtering:

    * `?search=keyword` (search by filename or metadata),
    * `?tag=ProjectX` (filter by tag),
    * `?speaker=Alice` (filter files where a certain speaker appears),
    * `?from=2025-01-01&to=2025-04-01` (date range filter),
      etc. The response is a list of file metadata objects (ID, name, duration, upload date, maybe a short snippet of transcript or summary, processing status).
  * `GET /api/files/{file_id}`: Get detailed info about a specific file. The response includes:

    * File metadata (name, uploaded by, duration, etc.),
    * **Transcript data:** perhaps structured as an array of segments, e.g.:

      ```json
      "transcript": [
         { "start": 0.0, "end": 5.2, "speaker": "Alice", "text": "Hello, how are you?" },
         { "start": 5.2, "end": 9.8, "speaker": "Bob", "text": "I'm fine, thank you." },
         ...
      ]
      ```

      Speakers are identified by name or an auto-generated label if unknown (e.g., "Speaker 1"). Each segment has timestamps.
    * **Comments:** list of comments with user, text, timestamp (if any).
    * **Tags:** list of tags attached to the file.
    * **Summary:** if available, the text of the summary.
    * **Analytics:** e.g., speaker talk ratios, sentiment summary, keywords (if computed).
      This is the primary endpoint the front-end calls to populate the file detail view.
  * `DELETE /api/files/{file_id}`: Delete a file and all associated data (transcript, comments) for that user. (Possibly requires confirmation/2-step in UI.)
  * `PUT /api/files/{file_id}`: Update file metadata. Could allow renaming the file or adding/removing tags via a JSON payload.

* **Transcript and Speaker Editing:**

  * `PUT /api/files/{file_id}/transcript`: Edit the transcript segments. The client can send an array of segments with edits (changed text or merged/split segments). For example:

    ```json
    {
      "segments": [
        { "segment_id": 456, "text": "Corrected text...", "speaker": "Alice" }
      ]
    }
    ```

    The server will update the transcript in the database. If speaker labels are changed, it may also update the speaker mapping (and possibly re-index search data). This supports manual correction of the transcription.
  * `PUT /api/files/{file_id}/speakers`: Change speaker labels for the file. The client can send a mapping of old speaker label to new name (or to an existing global speaker ID). E.g. `{ "Speaker 1": "Alice" }`. The backend will update the transcript segments and potentially link “Speaker 1” segments to the global “Alice” profile (creating one if needed).
  * (Alternatively, these edits could be combined in one endpoint or done via the same `transcript` endpoint, but logically we separate text edits and speaker re-labeling.)

* **Comment APIs:**

  * `POST /api/files/{file_id}/comments`: Add a comment. Expects JSON like `{ "text": "...", "timestamp": 123.45 }` (timestamp optional). Saves the comment associated with that file (and current user as author). Returns the created comment with an ID and timestamp.
  * `GET /api/files/{file_id}/comments`: Retrieve all comments on that file. (This could also be included in the file detail GET to reduce requests.)
  * `DELETE /api/files/{file_id}/comments/{comment_id}` or `PUT` for editing a comment could be provided as well, depending on needs (e.g., user can delete their comment).

* **Tag APIs:**

  * `POST /api/files/{file_id}/tags`: Add a tag to the file (if we don’t allow arbitrary text in the same endpoint as file update). E.g. payload `{ "tag": "Meeting" }`. Alternatively, the `PUT /api/files/{id}` could contain tags.
  * `DELETE /api/files/{file_id}/tags/{tag}`: Remove a tag from the file.

* **Search API:**

  * `GET /api/search`: Perform a search query across transcripts (and optionally file names). Query parameters could include:

    * `q`: the query string (what the user typed).
    * `speaker`: filter by speaker name,
    * `tag`: filter by tag,
    * etc., similar to the file list filters.
      The backend will translate this to OpenSearch queries. The response might look like:

    ```json
    {
      "results": [
        {
           "file_id": 123,
           "filename": "Meeting with Alice",
           "snippet": "Alice: Hello, how are you? ...", 
           "match_time": 0.0
        },
        {
           "file_id": 124,
           "filename": "Project Update",
           "snippet": "… key topic was artificial intelligence …",
           "match_time": null
        }
      ]
    }
    ```

    Each result could include a text snippet highlight where the query matched (OpenSearch can provide highlight info), and possibly a time offset if applicable (e.g., if we return a specific segment match within a file, we include start time of that segment so user can jump in). If the search is semantic, we might just show the top relevant segments/text.
    This endpoint enables a global search bar in the UI to find content in any file.

* **Speaker Profile API:**

  * `GET /api/speakers`: List the known speakers for the user (or organization). Each entry might have an `id`, `name`, and maybe a list of file IDs or sample quotes for context. E.g. `{ "speaker_id": 10, "name": "Alice", "appearance_count": 5 }`.
  * `POST /api/speakers`: Create a new speaker profile (this might not be commonly used, since profiles are created automatically when new voices are encountered, but an admin could pre-create or manually add one with an audio sample).
  * `PUT /api/speakers/{id}`: Update a speaker’s name or merge another speaker into this one. For instance, if two profiles were mistakenly separate and the user wants to merge them, the payload might indicate a merge action.
  * In many cases, explicit speaker profile management might be minimal in the API, as it can be handled via the file-level speaker editing. But an interface exists for admin or advanced management of speaker identities.

* **Summarization & Analytics API:**

  * If summaries are generated automatically, they’ll be included in the file detail. But we may also provide:
  * `POST /api/files/{file_id}/summary`: Trigger (or re-trigger) generation of a summary for the file. If the summary was not auto-created or if the user edited the transcript and wants an updated summary, this endpoint enqueues a summarization task. Returns a job ID or status.
  * `GET /api/files/{file_id}/summary`: Get the summary text (and perhaps metadata like model used, or length). (This might be redundant if `GET /files/{id}` already contains the summary.)
  * Similarly, for translation:

    * `POST /api/files/{file_id}/translate?lang=en`: would trigger translation of the transcript to English (if original was non-English).
    * `GET /api/files/{file_id}/translate?lang=en`: get the translated text (or it could be included in file detail as an alternate transcript).
  * Analytics (talk time, sentiment) could either be precomputed and stored (hence delivered via file detail), or computed on request. If on request:

    * `GET /api/files/{file_id}/analytics`: returns JSON with speaker durations, sentiment scores, keywords. But likely these are computed at transcription time and stored, so an extra endpoint isn’t necessary.

* **Export API:**

  * `GET /api/files/{file_id}/export?format=srt`: Export transcript in specified format. The server will format the transcript accordingly:

    * **TXT:** plain text with or without speaker labels.
    * **PDF:** returns a PDF file (setting appropriate content-type). The server will generate a PDF on the fly (using a template to include perhaps the file name, list of speakers, then the transcript).
    * **SRT/VTT:** as subtitle files. For SRT, include indices and timecodes in HH\:MM\:SS,millisecond format. For VTT, slightly different formatting. The content is generated based on transcript segments.
  * This might directly stream the file download to the browser. Alternatively, it could be a background task if generation is slow (PDF might be a bit slow), but generally should be quick. We ensure the API is protected (only the owner or admin can export that file’s transcript).

All endpoints require proper **authentication** (except login/register). The JWT token is expected in the `Authorization: Bearer <token>` header. FastAPI’s dependency system will verify the token and user permissions for each request. For example, attempting to access someone else’s file ID will return 403 Forbidden.

**Data Formats:** JSON is used for request and response bodies (except for file upload which uses multipart/form-data and export downloads which return binary). Timestamps are in seconds for media positions, and date-times are in ISO format for metadata. Speaker identities in transcripts might be represented by a name string or an ID – in responses we’ll likely use the human-readable name (with a default like “Speaker 1” if not named). In requests (like editing), the client might refer to them by the temporary label or by a known ID.

We also design the API to be **RESTful** and intuitive. For instance, using nouns like `/files`, `/comments`, and HTTP verbs (GET for read, POST for create, PUT/PATCH for update, DELETE for delete). This makes it easier to maintain and possible to integrate with other tools (even CLI or third-party apps).

**Example Workflow (Upload to Transcript):**

1. `POST /api/files` with file -> returns `{ file_id: 123, status: "processing" }`.
2. User’s UI starts polling `GET /api/files/123` waiting for `status: "completed"` or listens via WebSocket.
3. After processing, a worker updates the DB; now `GET /api/files/123` returns status "completed" and includes `transcript` and other data.
4. User fetches `GET /api/files/123` and gets the transcript and displays it.

**API and Integration with Frontend:** The Svelte app will have an API service layer that calls these endpoints, handling the JWT token automatically (possibly storing it in localStorage or a cookie). Real-time operations (like receiving a notification that transcription is done) might use a WebSocket connection to a `/api/ws/notifications` endpoint (not a REST endpoint, but a socket). On the server side, that could be implemented within FastAPI using Starlette’s WebSocket support, subscribing to task events.

**Error Handling:** The API will return appropriate HTTP error codes and messages for issues (400 for bad input, 401 for no auth, 403 for forbidden, 500 for internal errors, etc.). The front-end will handle these gracefully (e.g., show an error message if transcription fails). We’ll also implement retries or fallbacks in the Celery tasks and surface failure reasons to the user (e.g., “Transcription failed due to unsupported codec”).

Overall, the backend API is designed to cover all CRUD operations for the app’s data while deferring heavy computation to background tasks. This keeps the API responsive and scalable. The structure will also make it straightforward to add features (e.g., if we want to add an endpoint for merging two files’ transcripts or any new functionality, it fits into this REST pattern).

## 4. Database Schema (PostgreSQL & OpenSearch Integration)

The PostgreSQL relational database will store the core data about users, files, transcripts, and related metadata. We design the schema to normalize data where appropriate, but also allow efficient queries for the typical access patterns (e.g., fetching a transcript for a file, or listing files for a user). Below are the main tables in the database and their key columns:

* **Users** – stores user accounts.

  * `user_id` (PK, serial big int)
  * `username` (text, unique), `email` (text, unique)
  * `password_hash` (text) – securely hashed password.
  * `role` (text) – e.g., "user" or "admin".
  * `created_at`, `last_login` (timestamps)
  * `preferences` (JSON or separate fields) – e.g., notification settings.
  * (Note: Alternatively, we could integrate an OAuth provider, but here we assume local accounts.)

* **MediaFiles** – stores each uploaded audio/video file’s info.

  * `file_id` (PK)
  * `user_id` (FK to Users) – owner of the file.
  * `filename` (text) – original name or given title.
  * `storage_path` (text) – reference to where the file is in MinIO/S3 (could be a key or URL).
  * `upload_time` (timestamp)
  * `duration` (float or interval) – length of media in seconds.
  * `language` (text) – detected language (e.g., "en", "es") from Whisper.
  * `status` (text) – processing status ("processing", "done", "error"). We can update this as Celery tasks progress.
  * `summary` (text) – (optional) store the summary text directly if short, or a foreign key to a Summaries table if long.
  * `translated_text` (text) – (optional) if we store an English translation of a non-English transcript.
  * We might also store `transcript_text` (full plain text) redundantly for quick preview or search, but since we have a separate TranscriptSegments table and OpenSearch, this might not be needed in Postgres.

* **TranscriptSegments** – stores the transcript broken into segments (utterances).

  * `segment_id` (PK)
  * `file_id` (FK to MediaFiles)
  * `start_time` (float) – start timestamp in seconds.
  * `end_time` (float) – end timestamp in seconds.
  * `speaker_id` (nullable FK to Speakers) – which speaker spoke this segment. If null or 0, it might indicate unknown or not yet assigned.
  * `text` (text) – the transcribed content of this segment.
  * This table can have an index on file\_id for quick retrieval of all segments for a file (to display transcript sequentially).
  * We expect multiple segments per file (for example, a segment could correspond to a sentence or a continuous speech by one speaker). By storing segments individually, we can allow fine-grained editing (edit a segment’s text or speaker).
  * If needed, we might include a sequence number or so to preserve ordering, but since start\_time can serve to order them, that suffices.

* **Speakers** – stores known speaker identities (voice profiles).

  * `speaker_id` (PK)
  * `user_id` (FK to Users) – if speaker profiles are per user. (In a multi-tenant system, each user has their own set of known speakers. Alternatively, this could be global if sharing, but likely per user.)
  * `name` (text) – e.g., "Alice", or default "Speaker 1" if not named by user.
  * `embedding_vector` (vector or bytea) – we could store the speaker’s voice embedding (e.g., a 128-d or 256-d vector from Pyannote). Postgres can store it as an array or binary; however, we might rely on OpenSearch for vector matching instead. But storing it here as well can allow quick re-generation or analysis.
  * `created_at`
  * Possibly fields like `description` or notes.
  * If a speaker appears in many files, they have one entry here, and many TranscriptSegments will reference this `speaker_id`. Initially, when a new voice is detected, we create a new Speakers entry (with a placeholder name).
  * If the user renames a speaker, we update the name here (and this flows to any associated segments on retrieval).

* **Comments** – stores user comments on transcripts.

  * `comment_id` (PK)
  * `file_id` (FK to MediaFiles)
  * `user_id` (FK to Users) – author of comment.
  * `text` (text)
  * `timestamp` (float, nullable) – if the comment is attached to a specific time in the media. Null or -1 if it's a general comment.
  * `created_at`
  * We index by file\_id to quickly retrieve all comments for a file. Comments are shown sorted by timestamp (with non-timestamped perhaps at end or beginning).

* **Tags** – We can have a simple schema for tags:

  * `tag_id` (PK), `name` (text, unique).
  * **FileTags** (association table): `file_id` + `tag_id` (composite PK) – indicating a file has a given tag.
  * Alternatively, we don’t even need a Tags table if we treat tags as free-form text. We could have a FileTags table with just (file\_id, tag\_text). This might duplicate tag text, but given tags are short and few, that’s fine. This avoids joining for tag name. For flexibility, storing tag text directly can be okay.
  * This design allows a file to have multiple tags, and tags to apply to multiple files (many-to-many).

* **Summaries** – If we want to store longer summaries or multiple types:

  * `summary_id` (PK)
  * `file_id` (FK)
  * `summary_text` (text or maybe mediumtext if very long)
  * `created_at`
  * `model_used` (text, e.g., "Mistral7B" or "GPT4" if later we allow different ones)
  * `lang` (if we support summaries in languages).
  * In simpler form, we might just store the summary text as a column in MediaFiles if it's one per file. But a separate table could allow versions (like short vs long summary, or re-summarize etc.). Initially, one summary per file is sufficient, which could be a column in MediaFiles.

* **Tasks/Jobs** (optional) – To track background job statuses (especially if we want a detailed jobs page):

  * `task_id` (PK, maybe Celery task UUID or our own)
  * `user_id`
  * `file_id` (nullable if a job isn’t file-specific, but most are tied to a file)
  * `task_type` (text, e.g., "transcription", "summarization", "translation")
  * `status` (text: "pending","in\_progress","completed","failed")
  * `progress` (maybe a percentage or step indicator)
  * `created_at`, `updated_at`, `completed_at`
  * `error_message` (if failed)
  * This table gets updated by Celery tasks (either directly via DB or via API calls from the task). The front-end can query this to get a list of recent tasks. However, Celery has its own state tracking if using a result backend, but storing it ourselves allows more control and the ability to show history even after tasks are done.
  * We could alternatively not have this table and simply use fields in MediaFiles (like status, and maybe separate flags for summary done, etc.), but a table allows showing tasks that are not file-specific too (if any).
  * For the MVP, tracking the file’s status in MediaFiles might be enough (e.g., file.status = "processing" or "done"). The “Jobs status” page could be derived from files that are in processing state for that user, plus maybe separate flags for other tasks.

* **Analytics** (optional) – If we want to store results like sentiment or speaker times:

  * We could have a **SpeakerStats** table: `file_id`, `speaker_id`, `talk_time_seconds`, `word_count` etc., precomputed after transcription.
  * A **Sentiments** table: `file_id`, maybe `speaker_id` (if we do per speaker), and an overall sentiment score or classification.
  * **Keywords**: `file_id`, `keyword` (text). Or just store as an array in a column in MediaFiles (Postgres can do text\[] or JSON).
  * These are not strictly necessary to store; they could be computed on the fly by scanning TranscriptSegments (for talk time) or by running an analysis function. But for efficiency, precomputing and storing when the file is processed is helpful.

Given the above, typical queries:

* To get a file’s transcript: join MediaFiles -> TranscriptSegments -> Speakers to fetch segments with speaker names. (We might also use an ORM; with an ORM like SQLAlchemy, we’d define these relations and fetch easily.)
* To update a transcript segment on edit: update TranscriptSegments where segment\_id = X.
* To get all files for user: query MediaFiles by user\_id (and maybe join FileTags, etc., if filtering by tag).
* The schema is designed to avoid extremely large text in one field (transcripts are split into segments to keep sizes manageable in each row and to allow indexing text if needed).

**OpenSearch Integration:** OpenSearch will have one or more indices:

* **Transcripts Index:** Suppose we create an index `transcripts` where each document corresponds to a **transcript or segment**. We have options:

  * One document per media file’s full transcript (with fields: file\_id, user\_id, full\_text, tags, speakers, date, maybe summary text). We can index the full\_text for keyword search. For semantic search, we can also store an embedding vector for the entire transcript or for chunks.
  * Or one document per segment (with fields: file\_id, speaker\_name, text, start\_time). This allows more precise search hits (you get the exact segment), and OpenSearch can even return highlights. But it could be a lot of documents if many small segments.
  * A compromise: index per file but also include maybe a few-sentence context around each occurrence for highlighting.
  * Considering performance and complexity, we likely do one doc per file for now:

    * Fields: `file_id` (so we know which file to open), `user_id`, `content` (the concatenated transcript text, or possibly just the transcript to feed to full-text analysis), `speakers` (an array of speaker names in that file, for filtering), `tags` (array of tags), `upload_time`, `title`.
    * Additionally, a `embedding` field (knn\_vector) which is an embedding of the content for semantic similarity. We can compute this by using a sentence transformer or embedding model on the entire transcript or the summary of it.
    * We will use OpenSearch’s k-NN plugin to store this vector and enable similarity search queries (like embedding the query and finding nearest docs).
    * With this index, a search query from the user will be formulated as a hybrid query: a match on `content` for keywords combined with a knn query on `embedding` for semantic. We can use a hybrid scoring to rank results. The top results give us file\_ids, and possibly highlight snippets (OpenSearch can return a snippet of text around the keyword match).
    * When returning to the UI, we’ll include maybe the snippet or the start time of the snippet. If OpenSearch can’t store segment start times easily with the text, we might instead post-process: e.g., if we get a highlight text from OpenSearch, we find that text in our TranscriptSegments in Postgres to get the timestamp. This requires an extra step but is doable.
    * If semantic search (vector) found something not by exact word, we might not have a snippet readily. We could in that case return the beginning of the transcript or the summary as context.

* **Speaker Embeddings Index:** We can create a separate index `speakers` for speaker vectors to aid identification:

  * Fields: `speaker_id`, `user_id`, `name`, `embedding` (knn\_vector).
  * When a new speaker embedding is extracted from a file, the system does a k-NN search on this index to find if a similar voice exists (within some cosine distance threshold). If a match above threshold is found, we assume it’s the same person and link to that speaker\_id; if not, we create a new document in this index (new speaker).
  * This way, the knowledge of known voices accumulates. (Note: Pyannote embeddings are typically multi-dimensional and require normalization; OpenSearch’s kNN can handle up to 16k dimensions, Pyannote might be 256d, which is fine.)
  * Because OpenSearch can handle vector search at scale, this approach will remain efficient even if the user has many speaker profiles.
  * We will also store `name` in the document so we can filter or search by name if needed (though for UI listing, we’d normally just use Postgres Speakers table; OpenSearch is mainly for the matching function here).

* (Optional) **Content Embeddings Index (Segments):** In future, for more fine-grained semantic search, we might store each segment or each paragraph of transcript as a separate doc with its own embedding. That way a semantic search query can directly retrieve the most relevant snippet, not just the whole file. However, this increases index size and might require more complex result grouping (to avoid showing too many segments from one file separately). For the initial design, we keep it simple with one vector per file or per file summary.

**Data synchronization:** Whenever a transcript is created or updated, we must update the OpenSearch index:

* After a transcription task finishes, the worker will send the full text and metadata to OpenSearch to index the new document. This includes computing a text embedding (we might use a pre-trained MiniLM or similar model within the Python code to get a vector).
* If a transcript is edited by the user, we should re-index that file’s document (to update the text content). This could be done synchronously on edit save or scheduled shortly after edit.
* When speaker names are updated, we update the `speakers` array field in the transcript document (so that a filter by that name still works). That means re-index or partial update in OpenSearch.
* When a new speaker is identified or an existing one merged, update the speaker index accordingly (add or update the speaker vector entry).
* Similarly, adding a tag to a file should trigger updating the OpenSearch doc for that file’s tags field.

To manage these, we might create **Post-save hooks or signals** in our application logic: e.g., after saving a TranscriptSegment edit or new tag, call a function to update the index. Alternatively, perform search index updates as part of Celery tasks (so as not to slow down user requests). For instance, an edit endpoint could quickly save to Postgres and then spawn a small Celery task to update OpenSearch in background.

**Capacity and indexing considerations:**

* Postgres will mainly hold text and metadata. Transcripts can be large (an hour of speech \~ 10k words). Splitting into segments helps; each segment might be a few seconds to a minute of speech. The `TranscriptSegments` table could have tens of thousands of rows per hour of audio. This is fine for Postgres. We should ensure queries remain fast by indexing `file_id` (which is common) and possibly `speaker_id` if we query by speaker.

* For OpenSearch, indexing entire transcripts means documents could be relatively large (a few pages of text). OpenSearch can handle that; we might want to tune the analyzer (we can use the default English analyzer for content, and maybe a Spanish analyzer if content language differs – or use a generalized multilingual analyzer).

* We will use the OpenSearch k-NN plugin for vector fields. We need to choose an algorithm (HNSW is typical for approximate nearest neighbor with high performance). OpenSearch allows specifying similarity metrics (cosine for embeddings). As an example, OpenSearch can store a `knn_vector` and we can do queries like:

  ```json
  {
    "query": {
      "bool": {
        "must": [
          { "match": { "content": "project update" } }
        ],
        "filter": [
          { "term": { "user_id": 5 } }
        ],
        "should": [
          { "knn": { "embedding": { "vector": [/* embedding of query */], "k": 10 } } }
        ]
      }
    }
  }
  ```

  And then do ranking combining BM25 score and vector similarity. We might also use OpenSearch’s newer **hybrid scoring** features to combine them more directly.

* The **Speakers** index in OpenSearch is straightforward: when matching, we do a kNN search with the embedding of the new speaker segment (extracted via Pyannote). If top result has distance below threshold, we consider it a match. If not, create a new doc. The threshold might be determined empirically (Pyannote might have recommendations or one can tune based on false positives).

**Relation between Postgres and OpenSearch:**

* Postgres is source of truth for transactional data. OpenSearch is a derivative data store for search purposes. If there’s any discrepancy, we can re-index from Postgres.
* We should plan a way to re-index all data if needed (e.g. a management command to iterate files and index them in OpenSearch, in case of mapping changes or data recovery).
* For now, synchronization will be maintained in code at the time of changes.

In summary, the database schema captures all necessary data – *users, files, transcripts (with speaker links), speakers, comments, tags, and tasks*. This aligns with the identified data categories (user accounts, transcript text, speaker data, transcription job status). The OpenSearch schema complements it by enabling advanced search on transcript text and speaker identities.

This hybrid approach (Postgres + OpenSearch) ensures we get the benefits of relational integrity for core data and the speed of search indices for retrieval. It also allows scaling reads heavy search load separately from the primary database.

## 5. AI Integration: WhisperX, Pyannote, and Local LLMs

This application heavily leverages AI models for transcription (ASR), diarization (speaker detection), and NLP (summaries, etc.). We integrate these as follows:

**Speech-to-Text with WhisperX:** WhisperX is an enhanced version of OpenAI’s Whisper ASR that provides word-level timestamps and can integrate with diarization. The pipeline for transcription will be:

1. **Audio Pre-processing:** When a Celery task begins transcribing a file, it first ensures the audio is in a suitable format (e.g., WAV or FLAC). If the upload is a video, we extract audio using FFmpeg. We might downsample or convert stereo to mono if needed (Whisper can handle stereo but diarization might prefer mono). FFmpeg can be invoked for this if needed.
2. **Running Whisper (via WhisperX):** We load the Whisper model (likely a large or medium model for good accuracy – this can be configurable). Because Whisper models are large, this will be done on a GPU if available for speed. WhisperX will produce the transcript text with **timestamps for each word or phrase**. We will likely use the “segments” output from Whisper, which might give us chunks of text with start/end times.
3. **Speaker Diarization (Pyannote):** After obtaining the transcript, we need to assign speaker labels to segments. Pyannote is used to perform speaker diarization on the audio:

   * We load a pre-trained diarization pipeline such as `pyannote/speaker-diarization-3.1`. This model, when given the audio, will return a set of time intervals with speaker tags (e.g., segment1: 0-5s Speaker A, 5-8s Speaker B, 8-12s Speaker A, etc.). It essentially answers “who spoke when”.
   * The diarization model uses speaker embeddings internally to cluster speaker turns. Pyannote is known for high accuracy in this domain.
   * The diarization output might label speakers as "SPEAKER\_00", "SPEAKER\_01", etc. These are temporary IDs for that file.
4. **Aligning Transcripts with Speakers:** We then need to combine Whisper’s output (which has the text and exact times) with Pyannote’s speaker segments (which have times and speaker IDs). We perform an **alignment** step:

   * Iterate through the Whisper transcript segments (or even word timestamps) and for each segment time, find which diarization speaker was active during that interval. Since both have time intervals, we assign the speaker that overlaps most with that segment.
   * If a Whisper segment covers a period where the diarizer says Speaker A then Speaker B spoke, we might split that transcript segment at the speaker change (to accurately label each portion).
   * The result will be a sequence of transcript segments each with a speaker label (from diarization). Essentially, we produce the “speaker-annotated transcript”. This answers “who said each line”.
   * This process can handle overlaps by choosing the speaker with longest overlap for each word/segment. Overlap is rare in many cases (over-talking), but Pyannote does attempt to detect it; in overlapping speech, we may attribute the segment to the dominant speaker or even mark overlapping speech separately if needed (for simplicity, we might ignore overlaps or mark them specially).
   * WhisperX may actually have a built-in integration for diarization (some forks allow passing a diarization model to tag words directly). If available, we’ll use that to simplify (it would essentially do the above alignment internally).
5. **Storing Transcript Segments:** Once we have segments with speaker info, we save them to the database (TranscriptSegments table). Each segment will have the text and the speaker (we’ll map Pyannote’s "SPEAKER\_00" to a speaker profile as described next).
6. **Speaker Identification (Cross-File):** For each unique speaker label in this file (e.g., Speaker\_00, Speaker\_01 from diarization), we determine if they match an existing known speaker:

   * We take one or more audio snippets corresponding to that speaker (Pyannote can provide an embedding for each speaker cluster). For example, the diarization pipeline might expose the average embedding vector for Speaker\_00. If not directly available, we can use Pyannote’s `Embedding` model on a representative audio segment for that speaker.
   * We then compare this embedding against our **Speakers** index (OpenSearch kNN or even a simpler cosine similarity in Python if small scale). If a match above threshold is found, we link to that speaker. If not, we create a new Speaker entry in the DB and add its embedding to the index.
   * This means if “Speaker\_00” in this file is within say 0.8 cosine similarity to the embedding of “Alice” from a previous file, we conclude Speaker\_00 = Alice.
   * The threshold can be tuned to balance false positives/negatives. We might start with a high threshold to avoid misidentification, meaning by default it will treat new voices as new speakers unless there’s a strong similarity to an existing profile.
   * When we create a new speaker profile, we may label it as “Speaker N” (next number) by default. The user can later rename it to a real name. Renaming in the UI updates the `Speakers` table and is reflected in transcripts of all files that reference that speaker.
   * We persist the embedding for future use. Possibly store multiple embeddings per speaker (from different files) to improve identification (this could be as multiple docs in OpenSearch or we update the speaker’s embedding to be an average).
7. **Result:** At this point, the file’s transcript is stored with speaker IDs that either point to existing profiles (with names) or new ones. The transcript text is stored and indexed. The user sees something like:

   ```
   Alice: Hello, how are you?
   Bob: I'm fine, thank you.
   ```

   instead of Speaker\_00/01.

This pipeline leverages open-source models to achieve an experience close to proprietary services like Otter.ai or AssemblyAI. **Combining Whisper ASR with Pyannote diarization yields a detailed transcript with speaker labels**, and using embeddings allows persistence of identities.

**Quality considerations:** Whisper (especially large-v2) is one of the most accurate ASR models available publicly, so transcription quality will be high. Pyannote is state-of-the-art for diarization, so speaker separation should be good even for multiple speakers or noisy environments. If needed, we can adjust Whisper’s decoding options (like beam size) or use noise suppression on audio to improve quality.

For performance, Whisper large can be slow; we might allow using Whisper **small or medium** model for faster but slightly less accurate transcription if the user prefers (this could be a setting). There are also faster alternatives like **Faster-Whisper** which is a reimplementation. We can consider using that to speed up processing by \~2x without loss of accuracy. In the roadmap, upgrading to newer models (like any Whisper v3 if released) or other libraries is considered.

**Summarization with Local LLMs:** Once a transcript is done, we generate a summary. Challenges: transcripts can be very long (thousands of words), and local LLMs have limited context window (most 1B-3B models might handle 1-2k tokens, 7B models up to 4k tokens). To summarize arbitrarily long text, we use a **chunking and iterative approach**:

1. **Chunking:** Split the transcript into chunks of, say, 500-1000 words (or roughly 2-5 minutes of speech) keeping segment boundaries intact. Each chunk can be summarized individually.
2. **Summarize Chunks:** For each chunk, prompt the LLM to produce a concise summary of that chunk. Because these models are local, we will run them on the same machine (preferably on GPU if the model fits, else CPU with optimized libraries). We might use a model like **Mistral 7B** or smaller; for 1-3B range, options include distilled versions of larger models or T5-based models for summarization. (For example, **Flan-T5 XL (3B)** could be a good candidate for summarization tasks and can run on a single GPU with 16GB memory.)

   * We load the model and tokenizer using Hugging Face Transformers in the worker. If GPU memory is constrained, we might use 8-bit quantization or a smaller model.
   * We craft a prompt for summarization (e.g., “Summarize the following conversation: ...”) or use a fine-tuned summarizer model if available.
   * The output for each chunk is an intermediate summary.
3. **Recursive Summarization:** If there are many chunks, we might then concatenate the intermediate summaries and summarize them again to get a final summary. This two-step (or multi-step) summarization is a known strategy to handle long documents by iterative refinement.

   * For example, if we had 10 chunks -> get 10 summaries -> join them, maybe split into two and summarize -> then one final summary.
   * This yields a coherent final summary that covers all parts.
4. **Store Summary:** Save the summary text in the DB (Summaries table or MediaFiles.summary). Also optionally index it in OpenSearch (so that search queries could also match the summary content).
5. This process is done in a background Celery task (`summarize_task`). It could be triggered automatically right after transcription, or deferred until the user requests it (depending on preference or resource constraints). We might make it optional for very long files if running on limited hardware.

**Local Models:** We prioritize using local (open-source) models so that the application can be self-contained (no external API costs or privacy concerns).

* For Whisper, the model weights are downloaded from open source (like Hugging Face) and loaded at runtime.
* For Pyannote, some pretrained models require acceptance of a user agreement (Pyannote pretrained weights on HuggingFace might need a token). We will include instructions to supply a HuggingFace token if required to download the diarization model.
* For LLM summarization, we will likely download a model like Mistral 7B or a smaller one and host it in memory. We could integrate **vLLM** or similar inference frameworks to optimize serving (vLLM can reuse KV cache for multiple prompts etc., but in our case batch is probably one at a time). Since summarization is not real-time interactive (it’s a background job), even if it takes, say, 30 seconds to a couple minutes, that is acceptable.
* Optionally, if the user has a more powerful model or an API key for OpenAI, we could allow configurable use of that to generate a summary with a larger model (that might be an extensibility item).
* Also note, if transcripts are non-English, we have two choices for summarization: either translate the transcript to English first (since our summarization model might be English-specific) or use a multilingual summarization model. Many open LLMs are primarily English-trained. A pragmatic approach: if the audio was in language X, we can have Whisper do an English **translation** (Whisper has a mode to directly output translation). Then summarize the English. We will incorporate that: the pipeline can produce both original transcript and an English translation (Whisper can do this in one pass if configured). We store both. Summaries will be done on the English version to ensure the LLM can understand it (unless we get a multilingual model).
* The summarization tasks should also be assigned to a Celery queue that can run on either CPU or GPU as available. If the GPU is busy transcribing, summarization could run on CPU or wait. We might serialize those tasks for one file to avoid heavy contention.

**Other NLP (Analytics):**

* **Sentiment Analysis:** We can use a small text classification model (for example, a distilled BERT for sentiment or even a rule-based VADER for quick analysis) to analyze each segment or each speaker’s lines. This can be done after transcription. For each speaker, we aggregate their sentiment (like count of positive vs negative statements) to say “Speaker A was mostly neutral, Speaker B had some negative sentiment at times”. This is stored as part of analytics.
* **Keyword Extraction:** We can use an algorithm like RAKE or KeyBERT (which uses embeddings to find representative keywords) on the transcript text. Alternatively, feed the whole transcript (or summary) to a prompt like “extract 5 key topics” using the LLM. Since we have the LLM anyway, that might be simplest: after summarizing, ask it for keywords. For offline processing, YAKE (Yet Another Keyword Extractor) or just frequency analysis excluding stopwords are straightforward. We might generate a set of top N keywords or key phrases and store them (to show as “Keywords: ...” in the UI, and possibly auto-tag the file).
* **Translation:** If the app detects the original language is not English, we might auto-run Whisper’s translation. WhisperX can be configured (by setting `task="translate"`) to output English text from the audio directly. If we go that route, we’d get two transcripts: one in original language, one translated. We need to decide which one to display by default (likely English if the user’s interface language is English). We will make both available (user toggle).
* For multiple languages support, if transcripts are in language X and user wants the interface in X as well, we could skip translation. The summarization could also be done in the original language if we have a capable model or by translating the input to English and then translating summary back (double translation may hurt quality).
* **Model Hosting and Caching:** All these models (Whisper, Pyannote, LLM) will be loaded within the Celery worker processes. We should structure the code so that the model is loaded once and reused across tasks to avoid re-loading overhead. For example, on worker startup, we can load Whisper into memory, and Pyannote pipeline as well (these could each take several GB of VRAM, so perhaps we load on first use and cache globally). Celery workers stay alive to process many tasks, so caching models is feasible. We just need to be careful with GPU memory if multiple workers on one GPU – likely we will run one worker per GPU to manage memory usage.
* **Resource Management:** GPU memory will be shared by Whisper and Pyannote and possibly the LLM. Whisper large + Pyannote can fit in 8-10GB. A 7B LLM can be another 10+GB. If one GPU can’t hold all simultaneously, we might offload some to CPU or sequence them. For instance, after transcription (Whisper) completes, we could free the Whisper model (or move to CPU) to free space for the LLM summarization if needed. Or use two GPUs if available (one for ASR, one for NLP tasks). Our design via Celery allows configuring task routing – e.g., we could have one queue bound to a GPU for ASR, another queue on a separate GPU for LLM, if hardware permits. Initially, assume one GPU does everything sequentially, which should be fine for moderate workloads.

**Validation and Accuracy:** We will test the pipeline with a variety of sample files to ensure:

* Transcripts align well with audio (WhisperX provides word-level alignment, which should be within tens of milliseconds accuracy).
* Speaker diarization is correct (speakers not getting mixed up). Pyannote is quite robust, but short utterances or overlapping speech can cause issues. Users can correct if needed.
* Speaker identification across files works (embedding similarity catches obvious same speakers). We’ll evaluate the threshold to minimize false matches. Possibly require multiple appearances before auto-matching to be sure.
* Summaries are coherent and capture key points (we might compare against manual summary for a test file).
* Multi-language: test with a non-English file to ensure we handle it (transcribe and translate properly).

By using well-regarded open-source models (OpenAI Whisper and Pyannote) and established techniques, the application benefits from state-of-the-art AI without external services. This approach is confirmed by community experiences – e.g., developers have successfully combined Whisper and Pyannote for speaker-labeled transcription, and this yields a quality solution comparable to cloud APIs.

## 6. Celery Task Queuing Strategy

To handle the various background operations, we utilize **Celery** as a distributed task queue. The strategy is to define different types of tasks for different workloads and configure Celery in a way that optimizes resource use (especially the GPU).

**Task Types:** We will define Celery tasks for at least the following functions:

* `transcribe_audio(file_id)` – Performs the WhisperX + diarization pipeline for a given file.
* `summarize_transcript(file_id)` – Generates summary for the transcript.
* `translate_transcript(file_id, target_lang)` – Optional task to translate transcript text.
* `generate_subtitles(file_id)` – Uses FFmpeg to burn subtitles into video (or to just produce an .srt if not already done).
* `analyze_sentiment(file_id)` and `extract_keywords(file_id)` – If we do analytics as separate tasks (could also be done inside transcribe task to save overhead).
* Possibly `notify_user(task_id)` – for sending notifications (though often we can handle notification logic outside Celery via websockets).

We will likely bundle some of these together to reduce overhead. For example, after transcription, the same task could immediately call sentiment analysis and keyword extraction (since it already has the text in memory). Summarization might be a separate task since it could take longer and we might want to schedule it with different priority.

**Queue Organization:** Celery allows multiple queues and routing tasks to specific queues/workers. We can leverage this:

* **`transcription` queue:** tasks that involve heavy ASR and diarization. These require GPU and are memory-intensive. We might run a dedicated worker (or workers) for this queue pinned to the GPU.
* **`nlp` queue:** tasks like summarization, translation, sentiment analysis. These also can use GPU (for the LLM or transformers) but could potentially be run on CPU if GPU is busy. If we have a second GPU, could assign this queue there. If not, it can share.
* **`io` or `utility` queue:** tasks that are mostly I/O or light CPU, like `generate_subtitles` (FFmpeg is CPU but not heavy CPU relative to ML) or sending email notifications if we add that. These could be handled by a separate worker process that doesn’t need GPU at all.
* Initially, we might keep it simple with one default queue for all, and later separate as needed.

**Concurrency and Scaling:**

* Each Celery worker can run multiple tasks concurrently (threads or processes), but since our tasks are heavy (and often not thread-safe due to GPU usage), we will likely run one task at a time per worker (especially for GPU to avoid contention). We can configure Celery worker concurrency to 1 or 2 depending on if we allow multiple CPU-bound tasks in parallel.
* If the server has multiple GPUs, we can run one Celery worker process per GPU, each listening to the transcription queue but configured to use a specific CUDA device (set an environment variable like `CUDA_VISIBLE_DEVICES=0` for one worker, `1` for another, etc.). We would also route tasks to specific workers if needed. Simpler: if multiple workers are identical, the tasks themselves can pick an available device at runtime.
* Celery supports scheduling and chaining: for example, we might chain `transcribe_audio.s(file_id) | summarize_transcript.s(file_id)` so that once transcription finishes, summarization runs automatically. Alternatively, handle this logic in the transcription task (after finishing, call delay on summarize task).
* We will use Celery’s retry mechanisms for robustness: if a task fails (e.g., due to an out-of-memory or a transient error), Celery can retry it after a delay. For example, if Whisper fails once, we could retry maybe once more (with a smaller model fallback if memory issue).
* **Broker:** Using Redis as broker (for simplicity). Redis is lightweight and can also serve as Celery result backend to store task states. RabbitMQ is also fine; it’s more robust for complex routing. For our scale, Redis is easier to configure.
* If using Redis result backend, we can query task status via Celery’s AsyncResult (FastAPI could poll if needed). But since we maintain our own status in DB, that might be redundant. Still, setting up result backend can be useful for Flower monitoring or for waiting on tasks in tests.
* **ETA / Rate limiting:** We could schedule tasks at specific times (not needed here except perhaps schedule a nightly summary of all new content? Not needed). We could rate limit summarizations if we want to avoid too many at once if the LLM is heavy.

**Task Flow for Upload:** When user uploads a file, FastAPI does:

```python
task = transcribe_audio.delay(file_id)
```

This immediately returns a task ID. We can store that in our Task table with status “pending”. The Celery worker for transcription picks it up and sets status to “in\_progress”. When done:

* The task saves transcript to DB, etc.
* It could directly update the Task entry to “completed” and note finish time.
* It could also send a notification event (maybe by publishing to a Redis channel or using a callback to FastAPI).
* It might then trigger summarize: `summarize_transcript.delay(file_id)` (or chain as mentioned).
* The front-end will either poll an endpoint that reflects file status or use websockets.

**WebSocket Notification:** We can integrate Celery with notifications by using Redis Pub/Sub or a simple approach: FastAPI can expose an endpoint for task completion. Celery, after finishing a job, could do an HTTP POST to a FastAPI route (like `/api/internal/task_done`) with the result (there’s a risk if the API requires auth, we can set a special internal token or open it for local calls). Another method: use Redis pubsub - FastAPI could subscribe to a channel and forward messages to WebSockets. Celery can publish to that channel (since using Redis already, easy to use the same Redis).

* For example, at end of transcribe task, do: `redis.publish(f"user_{user_id}_notifications", json.dumps({...}))`.
* The FastAPI WS handler (running in an event loop) listens on `user_{user_id}_notifications` and when it gets a message, sends it to the connected client.

**Celery configuration:**

* We will configure Celery in the FastAPI app (so that tasks can be called via `.delay`). Typically, define a `celery.py` that initializes Celery with broker URL from config (redis\:// etc.) and autodiscovers tasks modules. Both FastAPI and the worker processes will import this.
* In Docker Compose, we’ll run `celery worker` command for the worker container, with something like `--concurrency=1 --queues=transcription,nlp` (subscribe to both queues). Or we might run two separate worker instances with `-Q transcription` on one and `-Q nlp` on another, if we want to segregate.
* We’ll also possibly run `celery beat` if periodic tasks needed (maybe not initially, unless we want daily cleanup tasks, etc.).

**Monitoring Celery:** We plan to deploy **Flower**, which is a Celery monitoring UI, to track tasks in real-time. Flower can be launched as a separate service in Docker Compose, connecting to the same broker. It provides a web interface to see queued, running, succeeded, failed tasks. This is mainly for admin debugging and monitoring, but can be very useful during development and operations. Flower is read-only monitoring (and the ability to retry failed tasks manually). We will restrict it behind admin authentication if exposing it.

**Result Backend:** If using Redis as result backend, tasks will have a state that can be fetched via Celery. The Task status page can leverage that or the DB. We might use both: Celery state for quick check, DB for persistent record.

* Example: FastAPI’s job status endpoint could do: `AsyncResult(task_id).status` and return that for latest state. But if the Celery result backend state is cleared after some time, a DB record is more permanent.
* For simplicity, our own Task table plus front-end notifications might suffice, so using result backend only for Flower.

**Serial vs Parallel tasks:** Transcribing a single file we may want to use multiple threads (Whisper itself can use torch’s GPU parallelism and we can’t easily split one audio across workers unless we manually chunk audio in parallel, but that complicates assembly and often Whisper is best run on full audio to maintain context). So one file = one task.

* But we can process different files in parallel if resources allow (e.g., two Celery tasks on two GPUs or sequentially if only one GPU).
* The system should be able to queue up many tasks (if user uploads many files, they line up). Celery handles the queuing via broker easily.

**Error handling in tasks:** Each task will be wrapped in try/except. If an error occurs (e.g., model file missing, or audio decode error):

* Log the error,
* Update the Task status to "failed" in DB,
* Possibly update file status to "error" (so UI knows something went wrong for that file).
* Optionally, send a notification that it failed.
* The user can then see an error state and possibly retry (we might allow a “retry transcription” button which calls the task again).
* Celery’s automatic retry could also be used for certain exceptions (like a network glitch in downloading a model).

By using Celery, we ensure that heavy processing does not block web requests and we can scale those workers horizontally. The design follows a common pattern for FastAPI + Celery, enabling the app to remain responsive. We will tune the Celery concurrency and queue setup as we test the workload characteristics.

This queuing strategy allows throughput to be increased by simply adding more worker containers (scale out) or upgrading hardware (scale up GPU or CPU). It gives flexibility to prioritize certain jobs (we could assign higher priority to shorter files or interactive tasks if needed by using Celery priorities or separate high-priority queue).

Finally, to ensure tasks do not overwhelm the system, we may impose some limits (like at most N concurrent transcriptions if memory is limited – effectively controlled by number of workers). If multiple users use the system, tasks will be queued fairly in order of submission (Celery can also schedule tasks immediately if multiple workers free). We might implement a simple fairness if needed (not letting one user queue 100 jobs and starve others – though with limited user count, not a huge concern initially).

## 7. Frontend (Svelte) Structure and Features

The frontend is built with **Svelte**, a modern reactive web framework, ensuring a fast and fluid user experience. We will structure the Svelte application into components corresponding to the features identified. Key aspects of the frontend design:

**Overall Structure:** We use a single-page app structure (could be SvelteKit or a rollup setup). There will be multiple **routes (pages)**:

* **Login Page:** A form for username/email and password. On submit, calls `/api/auth/login` and handles the JWT. On success, store the token (likely in `localStorage` or an HttpOnly cookie). Svelte will then route to the main app.
* **Media Library (Gallery) Page:** This is the homepage after login. It lists all uploaded files in a grid or list. Each item shows file name, maybe a snippet of transcript or summary, duration, tags, and an icon for processing status (e.g., a spinner if still transcribing, or a checkmark if done). There’s an upload button to add new media. A filter sidebar is present on larger screens to refine the list by date, tag, or speaker. A top search bar allows free text search (calls API search). This page corresponds to `GET /api/files` and displays those results.
* **File Detail Page:** When user clicks a file in the library, it navigates to `/file/123` (for example). This page contains:

  * The **media player** (audio or video element wrapped by Plyr for controls).
  * The **transcript view**: a scrollable list of transcript segments. We will style each segment as, e.g., **Speaker Name**: *transcript text*. Segments may be grouped by speaker (e.g., continuous speech by the same speaker can be one paragraph).
  * The transcript text is highlightable: as the media plays, the current segment or word is highlighted. We achieve this by listening to the player's timeupdate events (fires every few milliseconds). We maintain a pointer to the current segment index and update CSS class to highlight it (e.g., a yellow background). Because WhisperX gives word-level timing, we could highlight word-by-word, but that might be too granular; highlighting the whole current sentence or segment is visually sufficient.
  * The user can click on any transcript segment – we handle the click by seeking the player to that segment's start time.
  * If the user hovers a segment, we might show an “edit” icon if editing is allowed. Clicking edit could turn that segment’s text into an editable textbox (contenteditable or an <input> for the segment text). After editing, an “save” button calls the PUT transcript API to save changes.
  * The **speaker labels** next to segments might be editable too (maybe a pencil icon next to the speaker name at the top of a segment group). Clicking it could allow choosing a different name or merging speakers. Alternatively, provide a separate “Edit Speakers” button that lists speakers in the recording and allows renaming them (this would call the speakers API).
  * **Comments panel:** Below or alongside the transcript, we show comments. Each comment shows author, timestamp (if any), text. If a comment has a timestamp, it’s clickable to jump the player. We provide a form to add a comment: user can type text and optionally attach the current playback time (via a "link time" button which auto-fills the time). On submit, call POST comment API and then display the new comment.
  * **Tags UI:** Perhaps at the top or bottom of this page, show tags associated with the file as chips. A plus button allows adding a new tag (opens a small input to enter tag name, hitting Enter triggers API call). Tags could be removed by clicking an "x" on each chip (calls delete tag API).
  * **Summary section:** If a summary is available, we display it, maybe in a collapsible panel (since it can be several paragraphs). If it’s not available yet but in progress, we show a “Summarizing...” indicator. If it’s not created, perhaps a “Generate Summary” button that calls the API or triggers the task (this button could be hidden if we auto-generate).
  * **Analytics section:** e.g., a small panel showing "Speaker Talk Time: Alice 5min (50%), Bob 5min (50%)" and perhaps a simple bar or pie chart. We can use a Svelte chart library or just simple divs for bar lengths. Also a "Sentiment: Mostly Positive" or a few keywords listed. This gives a quick insight.
  * **Download/Export buttons:** A button to download transcript (maybe a dropdown with formats). Clicking e.g. "Export SRT" triggers a fetch to `/export?format=srt` and then a download. Similarly PDF or TXT.
  * **Notification of processing:** If the file was still processing, this page could show a big overlay “Transcription in progress…” with perhaps a progress bar (if we had progress info). Once done (via WebSocket or polling), it would populate the above content.
* **Search Results Page:** We might integrate search results into the library page (like the library list just shows filtered results when a search is performed). Alternatively, a separate route for search results listing files/segments matching. But likely same page, simply showing the list filtered.
* **User Settings Page:** `/settings` – user can update profile info. Possibly also list their known speakers and allow renaming/merging here in a centralized place (like "Speaker Management"). This page calls user APIs and speaker APIs. For speaker management: list all Speaker entries for that user (name and maybe sample files they appear in). Provide an input to change name, and perhaps a multi-select to merge (or a “merge” button that allows selecting two and merging).
* **Admin Dashboard Page:** Only visible to admins. Could show stats: total users, total files, total processing hours, maybe a list of recent tasks or a link to Flower. Also allow admin to list all files in the system or all speakers across users (if needed to manage).
* **Notifications UI:** Likely a small dropdown or side panel accessible via an icon (bell). It shows recent notifications, e.g., “Transcription of file X completed” or “Summary for file Y is ready.” This list can be built from either live events or polling the tasks DB. We will mark notifications as read when viewed.

**Component Breakdown:** We will create Svelte components for reusability:

* `FileItem.svelte` – displays a file in the gallery (with name, status, summary snippet).
* `FileList.svelte` – container of multiple FileItem, perhaps handles infinite scroll or pagination if needed.
* `UploadButton.svelte` – or a modal component to handle file selection and uploading. We’ll use the browser File API and send the file via fetch to `/api/files`. We might show a progress bar for upload.
* `Player.svelte` – wraps the Plyr library. There is a Svelte wrapper library available (like `svelte-plyr`) which we can use to simplify integration. If not, we manually include Plyr’s JS and CSS. The Player component takes a media URL (likely we will get a presigned URL or a route like `/api/files/123/content` that streams the file) and loads it in an <audio> or <video> tag. It sets up event listeners (timeupdate, play, pause). It also provides methods to seek to a time (for transcript click sync). We’ll ensure the controls show things like play/pause, timeline, volume, maybe playback speed options (Plyr supports these).
* `Transcript.svelte` – displays the transcript. Possibly composed of subcomponents: `TranscriptSegment.svelte` for each segment (with logic to highlight if active). This component subscribes to the player's currentTime (we might use a Svelte store for currentTime that the Player updates, so Transcript segments can react to it).
* If word-level highlighting is desired, TranscriptSegment might further break the text into <span data-start=...> per word to highlight precisely, but that could be overkill. We likely highlight per segment or sentence.
* `CommentList.svelte` and `CommentItem.svelte`, plus `CommentForm.svelte`.
* `TagList.svelte` and `Tag.svelte` components for the tags UI in detail.
* `Summary.svelte` and `Analytics.svelte` for those sections.
* `SearchBar.svelte` – at top of screen, binds an input and on enter (or as-you-type) triggers a search. Could dispatch an event or use a store for search query that the FileList listens to.
* `FilterSidebar.svelte` – contains inputs for date range (two date pickers), tag filter (maybe a multi-select of tags used so far), speaker filter (multi-select of known speaker names for that user). On change, calls the API or filters the list if the data is already loaded. More likely, we call API with query parameters, since filtering on the client would require we had all data loaded which might not scale.
* The sidebar will be collapsible on mobile. We use CSS grid or flex to layout the library with a sidebar.

**State Management:** We will use Svelte’s built-in stores for certain global state:

* An `auth` store to hold current user info and JWT token (if not using cookies). The auth store can also track if user is logged in or not to protect routes.
* A `notifications` store containing an array of notifications. This can be updated by a WebSocket event handler or polling.
* Perhaps a `currentFile` store when on the detail page, or we just pass data via props.

**Responsive Design:** We will ensure:

* On desktop, the library shows as multi-column grid with sidebar always visible. On mobile, sidebar might become a filter button that toggles a dropdown.
* The transcript and video player layout: On a widescreen desktop, we could place video and transcript side by side. On smaller or portrait screens, video on top, transcript below.
* Comments might be below transcript on mobile, but on a wide screen might float to the right or in a tab.
* Svelte’s reactivity and conditional blocks can be used with CSS media queries or using the `svelte:window` resize events to adjust layout or use CSS grid which auto-adjusts.

**Plyr Integration:** Plyr is a UI library that stylizes the HTML5 video/audio elements. We will:

* Include Plyr’s CSS (for styling of controls).

* Use the Plyr JS to enhance a `<video>` or `<audio>` element. Possibly use the `onMount` lifecycle in the Player component:

  ```js
  import Plyr from 'plyr';
  let videoRef;
  onMount(() => {
    const player = new Plyr(videoRef, { /* options like controls, speed settings */});
    player.on('timeupdate', event => {
       currentTimeStore.set(player.currentTime);
    });
    // similarly on play/pause if needed.
  });
  ```

  The `videoRef` is a bind\:this on the <video> tag.

* This will give us a nice UI and we can control it programmatically (Plyr exposes a `player.currentTime` setter to seek).

* We also will overlay subtitles on the video if possible. We can generate a VTT or SRT and load it as a track in the video element. Alternatively, since we have the transcript in the UI, we might not need an actual subtitle track element. But including one could allow the user to turn on native subtitles. We can create a VTT blob from the transcript and attach as:

  ```html
  <track kind="subtitles" src="data:... .vtt" default>
  ```

  or provide a URL to subtitles.
  However, since we have our own highlighting system, we might skip the native track and just rely on our custom highlight. But offering an exported VTT track in player could be nice if user wants to use the browser’s picture-in-picture or so with subtitles.

* Plyr also has an event for when user seeks or plays. We will consider if we need to handle that (like if user manually seeks, we might need to update highlight immediately by recalculating current segment).

**Security:** The front-end will include the JWT in API calls. If using cookies (HttpOnly), we ensure to include `credentials: 'include'` in fetch. For simplicity, maybe store JWT in a writable store and attach in an `Authorization` header for each fetch call. We might use a small wrapper around fetch to automatically include the header and handle 401 (e.g., redirect to login if token expired).

**Localization:** Initially UI texts are in English, but we could plan to support i18n if needed by using a library or simple dictionary of strings in Svelte. Also, the app deals with multilingual content (transcripts), but the UI labels (like "Summary", "Speaker") might need translating if the app is used by non-English speakers. We mark that as future enhancement.

**Testing UI:** We will test the UI manually and possibly with automated end-to-end tests. We’ll ensure the transcript scrolls correctly with the player (maybe implement auto-scrolling: when a new segment is spoken, scroll it into view if it’s not visible, unless the user has scrolled away manually).

**Performance optimization:** Svelte compiles to efficient JS. We will ensure not to re-render the entire transcript list on every time update (which happens 10+ times per second). We can optimize by only updating the classes on relevant elements. Svelte’s reactivity can handle this if we store an index of current segment; updating that store will re-render only the segments that depend on it. If that still is heavy, an alternative is directly manipulating DOM classes in the timeupdate event (bypassing Svelte reactivity for that part) since we know which element to highlight. But likely not needed for moderate lengths (thousands of segments updated 10x sec might be borderline; we’ll watch).

* If needed, throttle the UI updates (maybe only highlight at word boundaries or every few hundred ms).

**Using compiled build:** For development, we run `npm run dev` which serves the app at e.g. localhost:5000 with hot reload. We will configure CORS on FastAPI to allow that. In production, we run `npm run build` which produces static files (index.html, bundle.js, etc.). Those will be served by NGINX.

* We’ll ensure relative paths or correct base href so that the app can be served from root.
* Possibly, we might choose to integrate the Svelte build into a single Docker image with FastAPI (copy `build/` into a directory and let NGINX serve it). Or run NGINX separately with a volume containing the build. Either way is fine.

**PWA considerations:** If needed, we might later turn this into a Progressive Web App with offline capability (not priority now, but could be nice for offline viewing of transcripts).

**Accessibility:** We will use proper semantic HTML (the transcript can be a `<article>` with `<p>` per segment and speaker name perhaps as `<strong>` or something). Ensure color contrasts are okay (especially for highlighted text). Provide controls labels for screen readers on the player if needed.

By structuring the front-end with reusable components, the code remains maintainable. Svelte’s straightforward reactivity will make implementing features like live transcript highlight simpler. We avoid heavy state management frameworks because Svelte’s context and stores suffice. The UI will gracefully handle different states: loading (spinner while waiting for transcript), error (show error message), and interactive states.

In summary, the Svelte front-end will deliver a modern single-page application that complements the powerful back-end: it will allow users to intuitively navigate their transcriptions, search, and manage everything in one place, with a smooth, desktop-like experience in the browser.

## 8. Deployment and DevOps

Deployment will be containerized using **Docker Compose**, making it easy to run the entire stack in development and production environments. Each major service runs in its own Docker container, orchestrated by Compose (or in production, potentially Kubernetes or similar, but Compose is our initial target).

**Containers/Services:**

1. **FastAPI App Container:** A Docker image based on Python (for example, `python:3.10-slim`). We install our Python dependencies (FastAPI, Uvicorn, Celery, Torch, transformers, etc.) in it. This container when run can serve two purposes:

   * In one instance, run the FastAPI app (e.g., the entrypoint could be `uvicorn app.main:app --host 0.0.0.0 --port 8000`).
   * In another instance (from the same image), run Celery worker (entrypoint `celery -A app.worker worker -Q transcription,nlp -c 1` for example).
     We might create separate images for API and worker if needed, but usually they share code so one image is fine; just different startup command.
   * This image needs to include system libraries for AI (like FFmpeg CLI, and possibly libsndfile for audio, etc.). We’ll apt-get install ffmpeg inside it.
   * It also needs the ML model dependencies: PyTorch with CUDA support, etc. We might base on an official PyTorch image or install via pip (e.g., `pip install torch torchvision torchaudio --extra-index-url ...` for CUDA). Alternatively, use NVIDIA’s CUDA base image + pip.
   * **GPU support:** To use the GPU in Docker, we will use NVIDIA’s Docker runtime. In docker-compose, we set `deploy.resources.devices` or simply run with `--gpus all`. Compose v3 has `runtime: nvidia` for earlier versions. We'll ensure documentation for deployment includes installing Nvidia Container Toolkit on the host so that the container can access the GPU.
   * This container will have code for FastAPI endpoints and Celery tasks. We might call it `app` in compose.
2. **Celery Worker Container:** As mentioned, we might run the same image as FastAPI but with a different command. In docker-compose, we can define a separate service `worker` using the same build, command `celery -A app.tasks worker --queues=transcription,nlp --concurrency=1`.

   * We ensure this container also has access to the GPU (`gpus: all` if needed, or maybe only the fastapi container doesn’t need GPU access, just the worker).
   * We can scale the number of worker containers as needed by `docker-compose up --scale worker=2`.
3. **Broker (Redis) Container:** Use the official Redis image. In compose file:

   ```yaml
   redis:
     image: redis:7-alpine
   ```

   * No special config needed, default settings suffice (we’re not storing large data in Redis, just queues).
   * We will set environment variable in app/worker containers like `CELERY_BROKER_URL=redis://redis:6379/0`.
4. **PostgreSQL Container:** Use official Postgres image (e.g., `postgres:15-alpine`). We will provide environment for default DB name, user, password. In dev, these can be simple defaults. In prod, secure values via env or secrets.

   * Mount a volume for data durability (so the DB data persists if container is recreated). E.g., `volumes: ["pgdata:/var/lib/postgresql/data"]`.
   * On first startup, Postgres will init the database. We may use a migration tool (like Alembic) to set up tables. We can either run alembic from the app container (could integrate a step on startup or run a separate container for migrations).
5. **OpenSearch Container:** Use OpenSearch official image. OpenSearch requires more resources (at least 4GB RAM by default). In dev, we can run a single-node OpenSearch. Config:

   ```yaml
   opensearch:
     image: opensearchproject/opensearch:latest
     environment:
       - discovery.type=single-node
       - plugins.security.disabled=true
       - opensearch_java_opts=-Xms1g -Xmx1g
     ulimits:
       memlock: -1
     ports:
       - "9200:9200"
   ```

   * We disable security for dev (no auth) and single-node mode. In production, if using AWS OpenSearch or a multi-node cluster, config will differ.
   * We also ensure the `knn` plugin is available (the standard image includes it by default for OpenSearch).
   * We will have to index mapping creation either via code or a setup script. Possibly include an init step in the app to check if index exists, if not, create mapping for transcripts and speakers indices.
   * Mount a volume for OpenSearch data as well, if we want persistence.
6. **MinIO Container:** Use `minio/minio` image for dev. Configuration:

   ```yaml
   minio:
     image: minio/minio:latest
     environment:
       - MINIO_ROOT_USER=minioadmin
       - MINIO_ROOT_PASSWORD=minioadmin
     command: server /data --console-address ":9001"
     ports:
       - "9000:9000"
       - "9001:9001"
     volumes:
       - miniodata:/data
   ```

   * This starts a local S3-compatible server accessible at port 9000 (with a web console at 9001).
   * In dev we’ll use the provided credentials. In production, we likely will not run MinIO but instead use AWS S3 or similar. Our app will be configured with an S3 endpoint and credentials accordingly (perhaps environment like `STORAGE_ENDPOINT`, `AWS_ACCESS_KEY`, etc. that the app uses to connect via boto3 or minio client).
   * The FastAPI app needs to talk to MinIO: we’ll use the Python MinIO client or boto3. The `storage_path` we store might be an object key, and the actual URL can be constructed or we use presigned URLs for client direct access. Possibly simpler: serve downloads via FastAPI proxying from MinIO.
   * In compose, MinIO will be accessible by name `minio:9000` to the app.
7. **NGINX Container:** Use an Nginx image (possibly custom if we need to add config and static files).

   * We will create an `nginx.conf` that does:

     * serve the static files (Svelte app) from `/usr/share/nginx/html` (we’ll copy the built files there via Docker volume or building a custom image).
     * location /api -> proxy\_pass to fastapi container (e.g., `http://app:8000`).
     * location /ws or /api/ws -> proxy\_pass with `upgrade` for websockets to `ws://app:8000`.
     * Possibly also handle /media or /files content. If we want Nginx to directly serve the videos from MinIO, we could mount the MinIO bucket if MinIO is deployed on same host, but easier is to just route through FastAPI or have the front-end get a presigned URL to stream directly from MinIO (which bypasses Nginx).
     * If we want to avoid streaming large files through FastAPI, we can let the front-end talk to MinIO or S3 directly for the video content. MinIO’s web endpoint requires auth though. We can generate a presigned URL for the file and give it to the video player src – that’s a good approach to offload streaming.
   * TLS: We will in production use Let’s Encrypt certificates. Possibly not handled in container (maybe offloaded to a host ingress or a separate container like Traefik). But Nginx can do it if provided certs via volume. We can also configure Nginx to redirect HTTP to HTTPS.
   * The Nginx container will depend on the FastAPI container (so it doesn’t start before API ready).
   * In dev, we might not use Nginx; developers can run the front-end dev server and FastAPI with CORS.

**Environment Configuration:** We will have a `.env` file or environment variables for sensitive/configurable values:

* `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `HUGGINGFACE_TOKEN` (if needed for pyannote model), `OPENSEARCH_HOST` (if not default), etc.
* Docker Compose can reference these via `env_file` or `environment`.
* We must ensure the JWT secret and any other secret keys are set in production environment properly.

**Building Images:** We can create a multi-stage Dockerfile for the app:

* First stage: build the Svelte app (using `node:18-alpine` for example). It will npm install and npm run build. This outputs static files.
* Second stage: build the Python app (using `python:3.10-slim` or maybe `nvidia/cuda:11.8-cudnn8-runtime-ubuntu20.04` as base for GPU). Install system packages (ffmpeg, build-essential if needed for some pip packages like we might need libsndfile for soundfile).
* Copy in the requirements and pip install. Possibly use a requirements.txt or poetry. Also install `git` if we need to pip install from git (if WhisperX isn’t on pip, maybe we install from GitHub).
* Copy the Python source code.
* In the same image or as a third stage, we could combine Nginx and static files, but easier: we will serve static from Nginx container, so we need to get the built front-end files to Nginx. We can do that by either:

  * Using a volume mount in compose: after building Svelte, host has `build/` folder, mount it into Nginx at /usr/share/nginx/html.
  * Or create a small image for Nginx that includes the files (FROM nginx\:alpine, COPY build/ /usr/share/nginx/html/).
* We’ll likely use the latter for simplicity in production (immutable infrastructure).
* So we’ll have an `nginx.Dockerfile` that FROM nginx, COPY nginx.conf, COPY ./frontend/build/ to html.
* Alternatively, skip separate image and use volumes in production, but images are cleaner for deployment versioning.

**Running with Compose:** The docker-compose.yml ties it together. We define services: app, worker, redis, postgres, opensearch, minio, nginx. We link them via service names (Docker’s internal DNS). We'll set `depends_on` appropriately (e.g., app depends\_on postgres, opensearch, minio, and worker also depends on those; nginx depends on app etc.).
We open necessary ports:

* Nginx on 80 (and 443 if TLS, though might terminate TLS outside).
* Possibly expose MinIO 9001 in dev to use its UI (not needed in prod).
* Postgres port maybe not exposed externally (only internal).
* OpenSearch port maybe not exposed except for debugging.
* We'll use volumes for db and search data, as mentioned.

**GPU Setup in Compose:** For GPU, each container that needs GPU must be run with the NVIDIA runtime. In newer Docker Compose versions, we can specify:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - capabilities: [gpu]
```

However, Docker Compose might require `runtime: nvidia` under `deploy` or `devices`. Because it’s a single-node deployment, we might just run Compose with an override: `docker-compose -f compose.yml -f compose.gpu.yml up`, where compose.gpu.yml adds the runtime flags.
Alternatively, instruct users to run `docker-compose run --gpus all`.
We'll document it clearly.

**Scaling**: In production, if using Docker Compose on a single server, scaling is manual (increase worker count). For more robust scaling and high availability, we could move to Kubernetes:

* Each component becomes a Deployment/StatefulSet. The architecture is cloud-friendly (stateless app and workers, stateful Postgres and OpenSearch can be managed services or StatefulSets).
* But initially, Compose on a VM is sufficient.

**CI/CD:** We will set up a CI pipeline (perhaps GitHub Actions or GitLab CI) to build the Docker images and run tests (see Test Strategy below). On pushing to main or a release, it can build and push images to a registry. Deployment could then pull the new images and restart containers with zero/minimal downtime (maybe using Docker Compose restart or a rolling update strategy if using a Swarm/K8s).

**Configuration Management:** Use environment variables for anything that differs between dev/prod:

* e.g., DEBUG mode, allowed origins, external service endpoints, etc.
* We will have config in FastAPI reading env vars (perhaps via Pydantic settings).
* For example, in dev, `OPENSEARCH_HOST=http://opensearch:9200`, in prod maybe something else.
* Credentials: In production, put them in a .env that is not committed, or better, use docker secrets if orchestrator supports.

**Logging & Monitoring Setup:**

* The application (FastAPI and Celery) will log to stdout, which Docker captures. We can configure log levels via env (e.g., FASTAPI\_LOG\_LEVEL=info).
* We might mount a volume for logs if we want persistent logs on disk, but often aggregating via Docker logging or external systems is better.
* We will use an approach to monitor container health: possibly define healthchecks in Docker Compose (e.g., ping FastAPI `/health` endpoint periodically, if fails, restart container).
* We can also monitor memory/CPU usage of containers (maybe using cAdvisor or simpler, just rely on host monitoring).
* For Postgres, we ensure backups (maybe schedule a nightly dump via a cron container or use managed DB with automated backups).
* Deployment scripts should also consider migrating the database (if using Alembic, run `alembic upgrade head` on deploy).

**Reverse Proxy & Domain:** If deploying on a domain (say transcript.app), we point DNS to the server. Nginx will be configured with that server\_name and an SSL certificate. Possibly use Certbot container to get Let’s Encrypt certificate. Alternatively, run a simpler setup behind a corporate firewall etc.

**MinIO/S3 in Production:** In a cloud deployment, we might skip MinIO and use actual S3. In that case, we don’t deploy MinIO container. Instead, configure the app to use S3 endpoint and credentials. The code likely uses environment to decide which. We can still keep the code abstract via boto3 (just endpoint difference).

* We need to ensure large file upload handling: using pre-signed URL might be necessary if we foresee very large files and we don't want to send through FastAPI. But if behind Nginx and on same network, uploading via FastAPI is okay as it streams to MinIO chunk by chunk (we’ll use async streaming).
* Alternatively, the front-end could do direct upload to S3 with a presigned URL approach. But that complicates front-end, so initially, API as proxy is fine.

**Auto-scaling Consideration:** In a more advanced scenario, if heavy usage:

* The Celery workers can be scaled out by running on separate nodes and connecting to same Redis broker. That’s straightforward if using something like AWS ECS or K8s HPA triggered by queue length.
* OpenSearch can be scaled to multi-node (we’d use a managed service or cluster).
* Postgres can scale reads with replicas and writes by vertical scaling or sharding if needed later.

For now, our DevOps plan is:

* Use Docker Compose in dev (on localhost with maybe environment DEV=true enabling CORS, etc.).
* Use Docker Compose on a production server (maybe behind an Nginx on host or the container itself).
* Monitor containers with tools like Portainer or plain logs.
* Use version control and CI to manage updates.

**Developer Experience:** We will allow volume mounts in dev so code changes reflect without rebuilding (e.g., mount the app code and run uvicorn in reload mode for development). The compose file can have a service for dev app (with reload) separate from prod app configuration. Similarly, front-end can be run outside container for hot reload connecting to dev API.

**NGINX static strategy:** We have to deliver the Svelte compiled files. We will:

* After building front-end, ensure those files are either copied into Nginx image or volume-mounted. We'll prefer copying in image for a controlled environment (versions match).
* Nginx config will have:

  ```
  location / {
    try_files $uri $uri/ /index.html =404;
  }
  ```

  to serve the SPA (since it’s client-side routing maybe, although if using hash routing or something not needed).
  We handle history mode by redirecting to index.html.

**Service Startup Order:** Compose will bring up Postgres, Redis, OpenSearch, MinIO, then app and worker, then Nginx last. We might want the app to wait a bit for Postgres and OpenSearch to be ready. We can add a startup script in the app container that pings those services until available (or use `depends_on` which doesn’t guarantee readiness, just start order). Possibly utilize healthcheck or a small wait loop.

**Lifecycle management:** If we update the application:

* We build new images, then do `docker-compose down && docker-compose up -d` (with perhaps zero downtime if using a more advanced approach like replacing containers one by one behind a load balancer; for one server that’s tricky without downtime).
* Because tasks could be running, we might want to signal Celery to stop accepting new tasks (`celery control shutdown` or we simply let them finish before bringing containers down).
* For stateful services (Postgres, OS, MinIO), their data persists in volumes, so upgrade images carefully (we might ensure compatibility of versions).
* We will document backup procedures for the database and possibly the MinIO data (though if using S3, that has its own durability).

In conclusion, the DevOps plan uses widely-used images and a straightforward Docker Compose setup to ensure the app is reproducible across environments. By containerizing, we avoid “it works on my machine” issues and encapsulate dependencies (like the exact version of CUDA libraries needed for torch). The plan is designed for both local ease-of-use and production reliability, with attention to data persistence and security (only exposing necessary ports, using environment secrets).

We will also include monitoring/telemetry in the next section to complement this deployment.

## 9. Monitoring and Logging Plan

To maintain and troubleshoot the application, we set up monitoring and logging mechanisms across the stack:

**Application Logging:**

* The FastAPI app will use Python’s logging to record events. We’ll set it to INFO level in production. Key events like user logins, file uploads, task submissions, and errors (tracebacks) will be logged. These logs go to stdout (by default in uvicorn, and we can configure a logging format JSON or text). Docker captures stdout/stderr, which can be viewed via `docker logs` or aggregated by a log system.
* The Celery workers also emit logs for task start, success, failure. We will add logging in our task functions to note when transcription starts for a file, when it ends, how long it took, and any exceptions. Celery will log retries as well. These logs also go to container stdout.
* We may mount a volume and log to a file for persistence beyond container restarts, but typically a centralized approach is better (see below).

**Centralized Logging (optional):** In a production environment with many containers, it’s useful to aggregate logs. Options:

* Use the ELK (Elasticsearch, Logstash, Kibana) or EFK (with Fluentd or Filebeat). We could deploy a **Filebeat** to collect Docker logs and ship to an ELK stack. Given we already have OpenSearch, we could use it as the log store: Filebeat could send logs into an index in OpenSearch.
* Alternatively, use a SaaS logging service or simpler, logs to files and a tail system. But likely, an OpenSearch index for logs with Kibana or OpenSearch Dashboards for viewing would be good.
* This is a bit heavy, so maybe not initial phase, but it’s planned if needed.

**Error Tracking:** We will integrate an error monitoring tool such as **Sentry** or similar:

* Sentry has a Python SDK which we can add. It will catch unhandled exceptions in FastAPI and Celery and send to a Sentry server (self-hosted or cloud). This will alert developers to errors and provide stack traces and context.
* Alternatively, rely on log monitoring and alerts, but Sentry gives more structured tracking (which tasks fail how often, etc.).

**Performance Monitoring:**

* For the backend, we might use middleware to log request execution time and track slow queries. For example, enabling SQLAlchemy echo in dev to see slow DB queries.
* If needed, integrate Prometheus:

  * Use **Prometheus client** in Python to expose metrics (like number of tasks processed, queue lengths, etc.). Celery can also expose metrics via a plugin.
  * Then run a **Prometheus** container to scrape those metrics from FastAPI (maybe at `/metrics` endpoint) and Celery (**Celery Task Monitoring:** We will deploy **Flower**, a web-based Celery monitoring tool, to keep an eye on task queues and statuses in real time. Flower provides a dashboard showing running tasks, completed tasks, and their results. We’ll run Flower as a separate container (connected to the same Redis broker) and restrict access to admins. This helps monitor if tasks are stuck or failing frequently, and allows manual task management (retries, revokes) if necessary.

**Infrastructure Monitoring:** For system-level metrics (CPU, memory, disk, GPU utilization), we will use:

* **cadvisor + Prometheus + Grafana (optional):** cadvisor can run as a container to expose metrics about other containers. Prometheus can scrape those metrics and we can set up Grafana dashboards. This provides insight like CPU usage of the Celery worker (important to see if we saturate CPU when running summarization on CPU, etc.), memory usage of the FastAPI app (to catch any memory leaks), and GPU utilization (Prometheus can scrape NVIDIA’s DCGM or nvidia-smi metrics with an exporter).
* If a simpler approach is needed, we might rely on cloud provider’s monitoring or basic Linux `docker stats` and nvidia-smi on the host to monitor resources.
* We will monitor disk usage of volumes (especially OpenSearch index size and Postgres) to plan scaling of storage.

**Alerts:** We will set up some alerting rules:

* If Celery queue length grows beyond a threshold (meaning tasks backing up, perhaps system is overwhelmed) – could alert to add more workers.
* If a critical error is logged (we can configure alerts via Sentry or via Prometheus alertmanager watching for log patterns).
* If disk space gets low or if CPU is constantly 100% for extended period.
* Basic uptime checks: Ping the health endpoint of FastAPI periodically (could use an external service or a simple cron curl) to ensure the service is up.

**Notifications:** In-app notifications (to the user) were covered earlier. Here we consider developer/operator notifications: Sentry (or similar) would email or message developers on exceptions. Prometheus Alertmanager can email or Slack notify when thresholds exceeded.

**Logging for Audit:** We will also log user actions such as login attempts (for security auditing) and file deletions. Admins might have an audit page to review recent actions (this could be as simple as filtering logs or a dedicated audit log table if needed for compliance).

**API Access Logging:** Nginx can log all HTTP requests. We’ll enable access logs in Nginx with format including response time. These logs can be parsed to identify usage patterns and any 4xx/5xx errors frequency. We might also have Uvicorn log requests, but Nginx logs give the source IP and consolidated view if we serve static too.

**Privacy:** Since we are dealing with possibly sensitive audio and transcripts, all logs and monitoring data that contain user content will be protected. For example, we will avoid logging raw transcript text or raw audio content anywhere. We might log “File 123 transcribed successfully” but not the transcript itself. Any PII in audio remains only in the transcript database and search index, which are secured. Admins with access to logs should not see user private data. (If needed, we could hash or omit such info in logs).

**Backup strategy:** Not exactly monitoring, but related to maintenance:

* We’ll schedule backups for Postgres (either via a cron job container dumping to S3 daily, or using managed backup if on RDS etc.). In case of a crash or data corruption, we can restore data.
* For OpenSearch, we can snapshot indices periodically to S3 as well (OpenSearch has snapshot functionality).
* MinIO/S3 data is inherently redundant (if using AWS S3 it’s multi-zone), but if self-hosted MinIO, we should back up that volume too (or use MinIO’s mirroring feature to another server).

In summary, our monitoring stack combines application-level monitoring (Flower for tasks, Sentry for errors) and infrastructure monitoring (Prometheus/Grafana for resource metrics). Logging is set up to be comprehensive and centralized, enabling us to trace issues and user activities as needed. With these measures, we can promptly detect anomalies (like a spike in task failures or memory usage) and ensure the system’s reliability and performance over time.

## 10. Test Strategy

A thorough testing strategy will be employed to ensure quality across the system, covering unit tests, integration tests, and end-to-end tests.

**Unit Testing (Backend):**

* We will write **unit tests** for individual functions and modules in the FastAPI and Celery code. Key areas:

  * **Transcription pipeline functions:** Test the alignment logic that merges Whisper transcripts with diarization output. We can simulate input data (fake Whisper segments and diarization segments) and verify that the output segments are correctly labeled with speakers.
  * **Speaker embedding matching:** Provide sample embedding vectors and a list of known embeddings, test that the matching logic correctly identifies the nearest speaker or creates new one when appropriate.
  * **API route logic:** Using FastAPI’s `TestClient`, test each API endpoint in isolation. For example, simulate a file upload with a small dummy audio file and ensure the API returns a processing status and creates a DB entry. (We might not run actual Whisper in unit tests, but mock the Celery task call to just mark as started).
  * **Database models:** If using an ORM or raw SQL, test that creating a MediaFile and related TranscriptSegments works as expected (e.g., constraints, cascades). Possibly use a test database (like SQLite or a throwaway Postgres schema) for this.
  * **Permissions:** Test that a user cannot access another user’s file via the API (e.g., GET /files/other\_id returns 403). We can set up two user accounts in the test DB and use two different auth tokens to simulate this.
  * **Utility functions:** e.g., timestamp formatting for subtitles, chunking logic for summarization, etc.
  * We’ll use `pytest` as our test runner, with fixtures to set up a test app, test database (with data loaded), and perhaps a dummy MinIO (could use MinIO in Docker for integration, or simply monkeypatch storage calls to use local disk for tests).

**Unit Testing (Frontend):**

* Using a framework like Jest or Vitest with Svelte Testing Library:

  * Test that components render with given props. For instance, `TranscriptSegment.svelte` given a segment prop shows the speaker name and text properly.
  * Simulate player time updates: we might fake the currentTime store change and assert that the correct segment gets a highlight CSS class.
  * Test form interactions: e.g., simulate typing a comment and hitting submit, ensure the form calls the provided action (which in tests can be stubbed to a dummy function and we verify it’s called with correct data).
  * Test that the search bar component triggers the search event/store update on enter key.
  * These tests help catch any logic in the front-end (like data formatting, conditional display) without needing a browser.

**Integration Testing:**

* **API Integration Tests:** We will spin up the FastAPI with a test database and possibly a test Redis and run test flows:

  * For example, a test that does the entire flow: register user -> login -> upload a small audio -> simulate Celery completing -> get transcript.
  * We can’t run Whisper on large audio in tests (too slow), but we can stub the transcription task to instead use a short fake transcript. One approach: configure a special mode or use dependency override in FastAPI for tests to use a dummy transcription function (that just writes a known transcript to DB immediately). Then the test can proceed to verify the rest.
  * Alternatively, we break it: test file upload API queuing (without executing task), then separately test that given an audio file we can run a function to process it end-to-end (perhaps on a very short audio clip, a few seconds, using a small Whisper model to not be too slow). This actually validates the ML pipeline. We might mark that as a special test (or use a smaller model and CPU if time allows).
  * Test search integration: index some known text to OpenSearch (or use an in-memory search stub) and then call the API and ensure the results formatting matches.
  * Integration test for summarization: feed a known transcript in DB, call summarize\_task (maybe directly, not via Celery in test), and check summary exists and makes sense (if using a deterministic small model or we stub the LLM to return a predictable output like "Summary: ...").
* **End-to-End (E2E) Testing:** Using tools like **Playwright** or **Selenium** to automate a browser:

  * Launch the entire stack (maybe in a docker-compose -f test.yml which uses test config) and then run a script that drives a headless browser.
  * Scenario: Open the app at login page, enter credentials (we can preload a test user in DB or register via UI), upload a small audio file (we can have a known small audio file, perhaps a 5-second WAV of two people). Then wait for processing indicator and eventually see transcript appear. Verify that the transcript text on screen matches expected (for the known audio, we can pre-compute the expected transcript).

    * If not wanting to rely on real Whisper in E2E, we might set the system to use a dummy transcription for a file with a certain name (like if file name contains "TEST", our Celery could short-circuit or load a prewritten transcript). This is a bit hacky, but ensures test consistency.
  * Interact with UI: play the audio, verify that the highlighted text changes (we can possibly use Playwright to evaluate DOM classes at certain time).
  * Add a comment via UI, then verify it appears.
  * Use the search box to search for a word said in the transcript, verify that the file is shown in results or the segment is highlighted.
  * Essentially simulate a user’s journey and assert the expected outcomes.
  * These tests are the most high-level and catch integration issues between front-end and back-end, and overall usability.

**Performance Testing:**

* We will do some performance testing outside of automated unit tests. For instance, take a 1-hour audio and run it on a staging environment to measure how long transcription takes, how memory usage behaves. This isn’t a pass/fail test but helps tune parameters (like maybe use medium model if large is too slow).
* We might also simulate concurrent usage: run a script to upload, say, 5 files concurrently and ensure the system can queue them and process without errors (and that nothing crashes due to race conditions like two tasks trying to write to same file etc., which shouldn’t happen as each file separate).
* If possible, use a tool like Locust or JMeter to simulate multiple users searching or viewing transcripts concurrently to see if any DB bottlenecks appear.

**GPU Testing:**

* We need to verify the application works on a system with and without GPU:

  * On a machine with GPU, ensure the Celery tasks indeed utilize it. We can check logs for torch stating “using CUDA”. And measure speed differences.
  * On a CPU-only machine (or if CUDA not available), the tasks should automatically fall back to CPU (our code will check `torch.cuda.is_available()`). We test that transcription still runs (albeit slower). This ensures we can run in environments where GPU isn’t present (maybe a small deployment or dev environment).
  * Possibly provide a config flag to force CPU in case we want to test that path on a GPU machine.
* We also consider different GPU models (if using in different envs, e.g., a test on a smaller GPU to ensure memory usage is within bounds).
* If multiple GPUs, test distributing tasks (like run two tasks simultaneously and see that we can target different GPUs if configured).

**Test Data:**

* We will collect a few short audio samples for testing:

  * A 10-second clip with two speakers saying known lines (to test diarization).
  * Clips in other languages to test multilingual (like a short Spanish sentence).
  * Edge cases: an empty audio or extremely low volume (should result in possibly empty transcript or a handled message).
  * Very short audio (<1 sec) to ensure system doesn’t break (Whisper might output nothing or some default).
* Also test large text handling: feed a long transcript (simulate by duplicating text) to the summarization function to ensure our chunking logic correctly splits it and produces a summary under length.

**Automated Test Execution:**

* Integrate tests in CI pipeline. Unit and integration tests run on each commit (likely using GitHub Actions with services like Postgres and maybe OpenSearch for integration).
* For CI simplicity, we might use an in-memory search stub instead of OpenSearch for tests, to avoid needing to spin up OpenSearch in CI (which can be heavy). Or use a small ES container in GitHub Actions.
* Frontend unit tests run with a headless browser environment in CI (using jsdom for Svelte tests, and Playwright can run in CI for e2e).
* We aim for high coverage on critical logic (especially anything with data processing).

**Test and Production Parity:** We will try to test in an environment as close to prod as possible (maybe a staging with same Docker images). Especially to test GPU code, we might need a runner with GPU (for instance, using specialized CI runners or manually testing on a GPU machine).

* We also test deployment scripts themselves (e.g., bring up docker-compose in a staging server as a dry-run before doing in prod).

**User Acceptance Testing:** If possible, have some beta users or team members use a staging deployment with real use cases and give feedback on accuracy and UI. This is not automated but ensures the system meets requirements in a practical scenario (e.g., test uploading a real meeting recording and see if the output is as expected in terms of diarization labeling, etc.).

By covering everything from single functions to the full user workflow, our test strategy will catch regressions and issues early. It gives us confidence that each deployment is stable. Whenever we add a new feature, we’ll add corresponding tests. For instance, when adding the export PDF feature, write a test that hitting the export endpoint returns a PDF with expected content (maybe parse the PDF text in the test). The comprehensive test suite (especially the integration and e2e tests) will be run before any release to ensure that all parts of the system work together as intended.

## 11. Scalability Roadmap

While the initial architecture is a single compose cluster, we have a plan to scale out as demand increases:

**Vertical Scaling (Phase 1):**

* We can assign more resources to the containers: e.g., move to a machine with a more powerful GPU (for faster transcription) or multiple GPUs, more CPU cores (to run more concurrent Celery tasks for NLP which might run on CPU).
* The database and OpenSearch can be given more memory or moved to bigger instances.
* This is the simplest step: tune Docker resource limits if any, or just host on a bigger VM.

**Horizontal Scaling of Services:**

* **Web/API Tier:** The FastAPI app is stateless, so we can run multiple instances behind a load balancer. In Docker Compose, we could scale `app` service to 2 and have Nginx round-robin (or use Docker Swarm ingress). More robustly, in Kubernetes, define a Deployment with multiple pods for FastAPI. This allows handling more concurrent user requests (useful if many users are streaming transcripts or searching simultaneously).
* **Celery Workers:** We can increase the number of Celery worker processes or machines. Since tasks are queued in Redis, any new worker that connects will start pulling tasks. For example, we could have multiple servers each running a Celery worker container. If using Kubernetes, we might use a HorizontalPodAutoscaler for the worker deployment based on queue length or CPU usage.

  * We can also separate responsibilities: e.g., have one group of workers specialized for transcription (with GPU access), and another group specialized for summarization/analysis (possibly CPU only). Celery supports routing keys to direct tasks to certain queues, which specific workers listen on. In a microservice style, we might even break the worker codebase: one service just running Whisper tasks, another running NLP tasks. But as long as it's one codebase, the queue separation is enough.
  * If we go multi-machine, ensure all have access to the same storage (MinIO/S3 solves that for files, DB is centralized, search is central).
* **OpenSearch Cluster:** For scaling search, OpenSearch can run as a cluster of multiple nodes. We can add nodes to increase capacity and throughput. If using AWS OpenSearch Service or self-managed cluster, we’d adjust shard count and replication. With multiple nodes, the vector search and text search can be partitioned to handle larger corpus.

  * If transcripts grow to millions of documents (could happen if system is used heavily), a single node might not suffice. Sharding will distribute data and querying load.
  * OpenSearch also can scale query throughput by adding coordinator nodes or using its built-in load balancing of search requests across nodes.
* **PostgreSQL Scaling:** Options:

  * Move to a managed cloud database that allows read replicas. If reading far outpaces writing (like many simultaneous users viewing transcripts), read replicas can offload reads. Our application would need to direct read-only queries to replicas (or use a proxy that does that).
  * For write scaling, an approach is sharding by user (each shard a separate DB for a set of users). But that’s only needed at massive scale. Alternatively, switching to a distributed SQL like Citus (for Postgres) or another DB is an option down the road if needed.
  * Likely, a single Postgres instance can handle quite large usage if properly tuned (especially since most heavy text search is offloaded to OpenSearch, Postgres mainly deals with moderate sized rows of text).
* **MinIO/S3:** For storage, if using S3, it’s inherently scalable. If using MinIO, we might consider moving to a distributed MinIO cluster or directly to S3 as usage grows. Large numbers of simultaneous uploads or downloads might require putting CloudFront (CDN) in front of S3 for faster delivery globally, etc., but that’s advanced scenario.

**Microservices Consideration:**

* The current design is modular enough that we could split the application into separate deployable services if needed:

  * **User Management Service** (auth, users) – rarely a bottleneck, so likely combined with API.
  * **Transcription Service** – could be separate: e.g., an API that just accepts an audio file and returns a transcript after done. We currently implement that via Celery tasks internally, but one could extract it out. However, since we want tight integration, we keep it internal for now.
  * **Search Service** – Instead of having FastAPI call OpenSearch directly, one could have a small service that queries OpenSearch and perhaps does additional filtering, returning results. This could allow independent scaling of search queries vs other API calls. But this might be overkill; direct queries are fine. If search load becomes huge, we could dedicate a separate FastAPI instance (or microservice in another language if needed for extreme performance) to handle search queries.
  * **Notification Service** – if in-app notifications become complex (say we add email or push notifications), that could be a separate process subscribed to a message queue of events (like a mini event-driven microservice).
  * We likely won’t need to fully split these, as the overhead of inter-service communication might not be justified. Celery already gives us a pseudo-microservice separation for background tasks.

**Kubernetes and Cloud Deployment (Phase 2):**

* For serious scaling and reliability, migrating to Kubernetes is natural. We’d create deployments for each component:

  * Deployment for FastAPI (with HPA scaling by CPU or requests).
  * Deployment for Celery workers (with perhaps two different deployments if we separate GPU vs CPU tasks).
  * StatefulSets for Postgres (or use RDS/Aurora) and OpenSearch (or use OpenSearch service).
  * Deployment for MinIO (or use AWS S3).
  * Service objects for internal comms and an Ingress for external (replacing Nginx container with an Nginx or Traefik ingress).
* Kubernetes allows better self-healing (restart containers on failure), rolling updates with zero downtime, and autoscaling. We will consider this once the usage grows beyond what a single node can handle easily.

**High Availability and Redundancy:**

* Currently, a single instance of each (DB, OS) is a SPOF. For production, we’d run Postgres in a primary/replica setup or use a managed highly-available DB. Similarly, OpenSearch cluster with at least 2-3 nodes (and replication) to avoid downtime if one node fails.
* The stateless parts (API, workers) are easy to duplicate for HA.
* Redis broker – could run in a replicated mode or use a cloud queue service. Redis usually can be run with a backup or use Redis cluster if needed. Alternatively, one could switch Celery broker to a cloud service like AWS SQS (Celery supports SQS) which is fully managed and HA. That might be something to consider at scale (remove the need to manage broker reliability).
* MinIO can be run in a distributed/erasure-coded mode across multiple nodes for HA, or rely on S3’s built-in HA.

**Scaling Specific Use Cases:**

* If one particular feature becomes heavily used, we can scale that:

  * e.g., If summarization (LLM) is slow and many users request it, that queue might back up. We could allocate more CPU cores or spin up dedicated summarizer worker pods separate from transcribers.
  * We could also consider using specialized hardware: e.g., a machine with a GPU for Whisper and another machine with more CPU or even an FPGA/accelerator for some tasks if needed (not likely needed, just concept).
* **Vector search scaling:** If using a huge number of speaker embeddings or transcripts, OpenSearch’s vector search might need tuning. We might consider approximate algorithms (HNSW by default is approximate) and adjust parameters for speed vs accuracy. We might also consider external vector DB like Faiss or Milvus if we needed separate vector service, but likely OpenSearch is fine.

**Optimizations:**

* We can implement caching to reduce load:

  * E.g., cache frequent search queries results for a short time if usage patterns show repetition.
  * Cache static content (CDN for the JS/CSS of front-end already handled by browser caching).
  * If users often replay the same file, the transcript is fetched from DB each time – not heavy, but we could store rendered transcript in a cache or static HTML (perhaps not necessary unless profiling shows DB is a bottleneck).
* Use of CDN for media content if global usage: currently, streaming from S3 or MinIO directly is fine. If clients are worldwide and media files are large, a CDN could dramatically speed up video load. We design such that it’s possible (since files are on S3, just put CloudFront in front).
* Partitioning users: In a multi-organization scenario, one could deploy separate instances per org if needed (if data isolation or scaling per tenant is easier that way). Our persistent speaker logic is per user anyway, but if one client had huge load, might isolate them on separate infrastructure.

**Future Feature Scaling:**

* If we add live transcription (streaming audio in real-time), that adds a different scaling challenge – requiring WebSocket handling at scale, and possibly a different speech model (like streaming ASR). We would consider a specialized service or using something like DeepGram’s streaming API if not doing locally. This is an extension that might require new microservices (like a stream processing service).
* If collaborative editing (multiple users editing a transcript) is introduced, we might need websockets and conflict resolution logic like Operational Transform or CRDT – that’s another dimension of scaling concurrency in state.

**Scalability Summary:** With the architecture chosen, we have a lot of levers to scale:

* We start with everything in one docker-compose on one machine, which is cost-effective for initial deployment.
* As usage grows, we move to multi-container distributed deployment (maybe cloud VMs for separate components, or Kubernetes).
* We ensure each layer (web, worker, search, db) can be scaled independently based on its bottleneck:

  * e.g., if transcription speed is the bottleneck, add another GPU worker node; if search latency is a bottleneck under heavy queries, add OpenSearch nodes.
* The use of standard technologies means we can use managed services (DBaaS, OpenSearch service, etc.) to help scale and reduce management overhead.
* The application’s design (task queue, stateless API) aligns with horizontally scalable patterns used in modern cloud architectures.

We will continuously monitor the system (as described) to know when to scale. For instance, if average queue wait time for transcription exceeds X, it's time to add another worker. Or if API response times climb due to load, scale out the API pods. The roadmap is to scale in a cost-efficient manner: small at first, then gradually increasing resources as needed, and refactoring into microservices only if the single codebase becomes a limiting factor for team or performance.

## 12. Optional Features and Extensions

In addition to core features, several optional features have been planned or can be added to enhance the system:

* **Export Formats (Transcripts & Summaries):** We have implemented export to TXT, PDF, and SRT/VTT. In the future, we might add more formats or customization:

  * **DOCX/Word Export:** Some users might want a Word document with the transcript, speaker names styled, etc. This can be done using a library like python-docx.
  * **JSON Export:** For developers, allow exporting transcript data as JSON (the same format as the API) for integration with other tools.
  * **Bulk Export:** If a user has many files, allow selecting multiple and exporting all transcripts into a single ZIP file (containing individual files or one combined).
  * These exports are straightforward once transcript data is there; it's mostly formatting.

* **Multilingual Support Enhancements:** Currently, if audio is in another language, we transcribe in original and optionally translate to English. We can extend this:

  * Allow user to request translation to other languages as well (say a French user might want French transcript from English audio, etc.). We could integrate models like M2M-100 or MarianMT for arbitrary translation, or use cloud translation APIs if accuracy needs to be higher.
  * UI localization: provide the web interface in multiple languages (internationalize the Svelte app using i18n libraries and have translation files for labels).
  * The diarization and speaker ID works language-independently (voice-based), so no changes needed there.
  * Possibly allow user to choose Whisper’s language or auto-detect — Whisper auto detection is good, but we might expose a setting if the user knows the language (to avoid detection errors).
  * We also ensure OpenSearch indexing handles other languages (could use language-specific analyzers for better tokenization; e.g., if indexing non-English text, ensure it’s not using only English stopwords).

* **Analytics & Insights:** We built basic analytics (talk time, sentiment, keywords). We can expand this:

  * **Conversation Analytics:** For meeting recordings, identify action items or important decisions. Possibly use the LLM to extract "Next steps" or "Questions asked" from the transcript.
  * **Speaker Emotion Tone:** More fine-grained analysis of emotion (happy, angry, etc.) using speech tone analysis (there are ML models to detect emotion from voice) in addition to textual sentiment. This could highlight if a speaker was excited vs upset.
  * **Keyword timelines:** e.g., if a keyword “budget” appears multiple times, show at which timestamps it appears (maybe a sparkline or markers on timeline).
  * **Search within analytics:** e.g., allow queries like "who talked about X?" – which could combine diarization with content search to answer that (involves search and filtering by speaker segments).
  * **Dashboards:** If a user has many recordings, an analytics dashboard could summarize things like “Total hours spoken per speaker across all meetings this month” or “Most discussed topics in your calls”.
  * These advanced analytics may require additional data processing tasks or periodic jobs to aggregate data.

* **In-App Notifications:** Currently, we plan basic notifications for job completion. We can enhance this:

  * Notifications for other events: e.g., “Your password was changed”, “A new version of the app is available” (for informing users of updates).
  * If we implement collaboration (multiple users in an org), notify when someone shares a file or comments on a file you uploaded.
  * Possibly integrate with email or SMS for certain notifications (with user preferences controlling it). E.g., email the transcript or summary to the user when ready (some users might like the summary in their inbox).
  * Use a library or service for push notifications if we later have a mobile or PWA that can send push.

* **Advanced Search (Semantic & Keyword):** We have hybrid search with OpenSearch. We might further improve search features:

  * **Fuzzy search** for slight typos in keywords (OpenSearch supports fuzziness).
  * **Synonym search:** e.g., configure OpenSearch with a synonym dictionary (so search for “USA” finds “United States” in transcripts, etc.).
  * **Question-Answering search:** Using an LLM, allow users to ask questions like “When is the project deadline mentioned?” and find the answer from transcripts. This would involve using an LLM with the transcript or using something like Haystack QA system on top of our search index.
  * **Combined Speaker+Content queries:** currently possible with filtering, but perhaps allow more complex queries like “find where Alice mentions marketing budget”.
  * **Vector search for similar audio:** We could index embeddings of entire transcripts (as we plan) and allow a user to pick one file and find other files with similar content (like “find related meetings”).
  * **Speaker search by voice sample:** maybe allow uploading a short voice clip and searching which files have that speaker (using speaker embeddings) – essentially the system already can do that if we integrate an endpoint to ingest an audio snippet, compute embedding and search the index.

* **Speaker Management Interface & Training:** We plan a basic interface to rename/merge speakers. Further enhancements:

  * Allow user to **upload a known voice sample** and label it (training a new speaker profile manually). For instance, feed a 1-minute audio of “CEO speaking” to create a speaker profile even before it appears in any uploaded file. Then when files with that voice are uploaded, it can tag it immediately.
  * **Train/Fine-tune speaker model:** If the user provides multiple samples of a speaker and maybe a name, we could fine-tune an embedding model or at least compute a robust centroid embedding. Pyannote’s pretrained model is usually sufficient, but if needed, one could adapt it on the specific voices (more relevant in huge deployments or if trying to improve a particular speaker’s detection).
  * **Verification vs identification:** Possibly implement speaker verification – the ability to confirm if two voices are the same. This could be an admin tool to verify merges (e.g., show spectrograms or have a confidence score).
  * UI improvements: show an audio snippet waveform for each speaker profile that the user can play to recall who it is (small snippet from a recording).
  * If an enterprise has a directory of people with some voice data, integration could label speakers automatically by matching to known company employees (that’s an advanced enterprise feature).

* **Security and Sharing:** Optional feature to allow **file sharing between users**:

  * A user could share a transcript with another user (read-only or with comment rights). This introduces the need for an access control list on files rather than just owner. We would extend the DB with a FileShare table or extend MediaFiles to have a `owner_id` and possibly a `shared_with` relation (many-to-many to Users).
  * Could also allow generating a public shareable link (perhaps protected by a token) for a transcript, so external people can view a read-only version.
  * This is a significant feature outside the core, but aligns with how real products work (collaboration on meeting transcripts etc.).

* **Administrative Features:**

  * **Admin Dashboard Enhancements:** Graphs of system usage (e.g., number of hours transcribed per day, active users, etc.), possibly using data from logs or tasks. Admin controls to manage content (delete inappropriate files, etc. if in a multi-user environment).
  * **User roles** could be extended to roles like “Manager” that can see transcripts of their team, etc., if we go in an enterprise direction.
  * **Billing support:** If this is offered as SaaS, integrate usage tracking (minutes of audio processed per user) and possibly a billing system. This would involve tracking usage stats in DB and an interface for payments – out of scope for now but something to keep in mind in design (ensuring we can log minutes processed per user easily, which we can from our task durations).

* **Real-time Processing (Future):** As a roadmap item, consider adding **real-time transcription** for live meetings:

  * This would involve streaming audio from client to server (via WebSocket or WebRTC) and chunk-processing it, sending interim transcripts back. It’s a separate pipeline possibly using Whisper’s streaming modifications or another model (since Whisper is not natively streaming except via chunking).
  * Could be a separate microservice or use the same workers with lower latency settings.
  * The UI could show live captions and after meeting ends, finalize and allow editing as usual.
  * This is complex and would be an extension for a future version if needed (essentially trying to compete with live captioning services).

* **External Integrations:**

  * **Calendar Integration:** For meeting recordings, maybe connect with Google Calendar or Outlook to fetch meeting info (participants, title) and auto-tag transcripts with that info.
  * **Nextcloud Integration:** As mentioned in that Reddit, some might want to ingest files from a Nextcloud folder. We could create an integration where if a file is added to a certain Nextcloud directory, our app picks it up via webhook or periodic scan and processes it. Similarly, could integrate with Dropbox, etc.
  * **API for third-parties:** Provide an external API key mechanism so other applications can programmatically upload files and retrieve transcripts (basically turning part of the system into a service). This would require rate limiting and API key management, but is doable by extending auth.

* **GUI Enhancements:**

  * We might add a waveform visualization of the audio under the player with speaker regions colored differently (some transcription tools show a timeline with colored blocks for each speaker turn). This can provide a quick visual overview of conversation dynamics.
  * A mode to collapse/expand transcript by speaker or jump to next speaker’s turn quickly.
  * Hotkeys for the player (e.g., press a key to insert a time-stamped comment at current time).
  * Dark mode UI (just theming).

Each of these features can be implemented incrementally. The architecture is flexible enough to support them:

* Additional Celery tasks for new processing (like keyword extraction we already considered).
* Additional tables for sharing or integrating external data.
* The front-end is modular to add new pages or modals (like sharing dialog).
* The search infrastructure can be expanded with new indices or models as needed.

We will prioritize based on user feedback. For example, if users strongly desire collaborative features, we’d implement sharing next. If they want deeper analytics, we’d focus there.

## 13. Future Roadmap and Extensibility

Looking ahead, we plan the following to ensure the project remains extensible and up-to-date with technological advances:

* **Continuous Model Improvements:** The AI field evolves rapidly. We will monitor new releases of Whisper or alternative speech models (like NVIDIA’s Nemo or whisper-small derivatives) and update the transcription engine for better accuracy or speed when feasible. The modular design (encapsulating transcription in a Celery task) allows swapping in a new model with minimal changes to the rest of the system. Similarly, for diarization, if a better open model or an efficient speaker embedding method emerges, we can integrate it in place of or alongside Pyannote.
* **Large Language Models Integration:** As local LLMs improve, we might integrate a larger model (e.g., 13B or 70B parameter model) for higher-quality summaries and Q\&A. We can do this by either hosting it if resources allow or by allowing an optional connection to an external API (like OpenAI’s GPT-4) for summary generation, if the user configures an API key. The system could be extended to have a “premium summary” option that uses a powerful cloud model for a better result.
* **Plugin Architecture:** We envision enabling third-party plugins or extensions. For example, a sentiment analysis plugin, or a translation plugin. This could be as simple as defining interfaces (maybe via Celery tasks or APIs) that can be developed separately and then registered. For instance, an organization could plug in a custom keyword extractor if they have specific domain jargon.
* **Mobile Application:** In the future, a mobile app (iOS/Android) could be developed for on-the-go access. Our backend is ready with APIs that a mobile app can consume. We’d ensure the authentication (maybe move to OAuth flows for mobile) and use something like React Native or Flutter for cross-platform. The mobile app might allow recording audio and directly uploading it, or receiving notifications when a transcript is done.
* **Real-time Collaboration:** Possibly treating transcripts like Google Docs where multiple users can edit or comment simultaneously. This would require websockets and conflict resolution for edits. Our current setup with websockets for notifications is a step in that direction. We might use something like Yjs or ShareDB to handle collaborative text editing on the transcript.
* **Additional Media Types:** Extending beyond audio/video, perhaps support **podcast RSS ingestion** (pull episodes, transcribe them), or telephone call recording integration, etc., depending on use cases. The transcription engine would be similar, just ingestion differs.
* **Security Enhancements:** If clients require on-premises deployment, we’ll containerize accordingly and perhaps support air-gapped deployment (no external internet needed – we already mostly satisfy that by using local models). We may undergo security audits and harden the system (prevent XSS in the front-end by sanitizing transcripts if needed before display, etc.). We’ll also add features like two-factor authentication for accounts, audit trails, and compliance with data protection regulations (e.g., ability to delete all data for a user on request).
* **Usage Analytics & Feedback:** We’ll add internal analytics to see which features are used, where users spend time (of course with user consent and anonymized). This guides what to improve. Also, an in-app feedback mechanism so users can easily report issues or suggestions (perhaps a “Send Feedback” button sending to our support email or GitHub issues).
* **Extensibility for Integrators:** We want to make it easy for developers to use parts of our system. Possibly provide a Python SDK or client library to interact with the API (for those who want to script uploads). Also clearly document the API (maybe add OpenAPI documentation and interactive docs from FastAPI).
* **Scaling to Enterprise:** If targeting enterprise clients, consider multi-instance setups: e.g., allow deploying separate worker pools for separate departments and centralizing results, or offering a management console to oversee multiple deployments. Also, incorporate user directory integration (LDAP/SSO) for corporate environments.
* **AI Ethics and Bias:** We will stay updated on biases in the models (e.g., if Whisper has trouble with certain accents or Pyannote misidentifies certain voices). We might incorporate feedback loops: if a user consistently renames a speaker that was auto-identified as a different person, we could retrain or adjust thresholds. Ensuring fairness (like not misidentifying speakers in a biased way) is important especially if used in sensitive contexts.
* **Alternate Interfaces:** Perhaps voice interface or bots – e.g., a chatbot that you can ask questions about your transcript (leveraging the transcript text and an LLM). Or integration with voice assistants to query your recordings (“Hey system, what did we say about Topic X in last meeting?”). This again would use the same backend but a different front-end interface.
* **Deployment Extensibility:** Support different deployment modes: Docker Compose (already), Helm chart for Kubernetes, maybe an AWS CloudFormation or Terraform module that sets up the whole stack (for clients who want one-click deployment on AWS with EKS, RDS, etc.). This makes it easier to adopt in various environments.
* **Backup and Data Migration Tools:** Over time, we’ll provide scripts to export all data for a user (for compliance or migrating to another system) and tools to import data if someone is coming from another transcription service. This gives users control and avoids lock-in, which is attractive for an open-source solution.

By following this roadmap, we ensure the project stays modern, scalable, and user-friendly. The modular foundation we built (separating concerns and using standard protocols) means each future enhancement can be integrated without massive rework. The focus will remain on maintainability, so any new feature should be built as an add-on in a clean way (e.g., new Celery tasks or new API endpoints) rather than hacks.

In essence, this project is positioned not just as a one-off app, but as a sustainable platform for audio intelligence – transcribing, understanding, and managing audio/video content. By prioritizing best practices and continuous improvement, the application will remain useful and relevant for years to come, easily adapting to the evolving landscape of AI and user needs.

--
-- PostgreSQL database dump
--

-- Dumped from database version 14.17
-- Dumped by pg_dump version 14.17

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: analytics; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.analytics (
    id integer NOT NULL,
    media_file_id integer,
    speaker_stats jsonb,
    sentiment jsonb,
    keywords jsonb
);


--
-- Name: analytics_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.analytics_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: analytics_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.analytics_id_seq OWNED BY public.analytics.id;


--
-- Name: collection; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collection (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    user_id integer NOT NULL,
    is_public boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: collection_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.collection_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: collection_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.collection_id_seq OWNED BY public.collection.id;


--
-- Name: collection_member; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collection_member (
    id integer NOT NULL,
    collection_id integer NOT NULL,
    media_file_id integer NOT NULL,
    added_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: collection_member_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.collection_member_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: collection_member_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.collection_member_id_seq OWNED BY public.collection_member.id;


--
-- Name: comment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.comment (
    id integer NOT NULL,
    media_file_id integer NOT NULL,
    user_id integer NOT NULL,
    text text NOT NULL,
    "timestamp" double precision,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: comment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.comment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: comment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.comment_id_seq OWNED BY public.comment.id;


--
-- Name: file_tag; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.file_tag (
    id integer NOT NULL,
    media_file_id integer NOT NULL,
    tag_id integer NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: file_tag_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.file_tag_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: file_tag_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.file_tag_id_seq OWNED BY public.file_tag.id;


--
-- Name: media_file; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.media_file (
    id integer NOT NULL,
    filename character varying(255) NOT NULL,
    storage_path character varying(500) NOT NULL,
    file_size bigint NOT NULL,
    duration double precision,
    upload_time timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamp with time zone,
    content_type character varying(100) NOT NULL,
    status character varying(50) DEFAULT 'pending'::character varying,
    is_public boolean DEFAULT false,
    language character varying(10),
    summary text,
    translated_text text,
    file_hash character varying(255),
    thumbnail_path character varying(500),
    metadata_raw jsonb,
    metadata_important jsonb,
    media_format character varying(50),
    codec character varying(50),
    frame_rate double precision,
    frame_count integer,
    resolution_width integer,
    resolution_height integer,
    aspect_ratio character varying(20),
    audio_channels integer,
    audio_sample_rate integer,
    audio_bit_depth integer,
    creation_date timestamp with time zone,
    last_modified_date timestamp with time zone,
    device_make character varying(100),
    device_model character varying(100),
    title character varying(255),
    author character varying(255),
    description text,
    user_id integer NOT NULL
);


--
-- Name: media_file_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.media_file_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: media_file_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.media_file_id_seq OWNED BY public.media_file.id;


--
-- Name: speaker; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.speaker (
    id integer NOT NULL,
    user_id integer NOT NULL,
    media_file_id integer NOT NULL,
    profile_id integer,
    name character varying(255) NOT NULL,
    display_name character varying(255),
    suggested_name character varying(255),
    uuid character varying(255) NOT NULL,
    verified boolean DEFAULT false NOT NULL,
    confidence double precision,
    embedding_vector jsonb,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: speaker_collection; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.speaker_collection (
    id integer NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    user_id integer NOT NULL,
    is_public boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: speaker_collection_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.speaker_collection_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: speaker_collection_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.speaker_collection_id_seq OWNED BY public.speaker_collection.id;


--
-- Name: speaker_collection_member; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.speaker_collection_member (
    id integer NOT NULL,
    collection_id integer NOT NULL,
    speaker_profile_id integer NOT NULL,
    added_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: speaker_collection_member_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.speaker_collection_member_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: speaker_collection_member_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.speaker_collection_member_id_seq OWNED BY public.speaker_collection_member.id;


--
-- Name: speaker_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.speaker_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: speaker_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.speaker_id_seq OWNED BY public.speaker.id;


--
-- Name: speaker_match; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.speaker_match (
    id integer NOT NULL,
    speaker1_id integer NOT NULL,
    speaker2_id integer NOT NULL,
    confidence double precision NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT speaker_match_check CHECK ((speaker1_id < speaker2_id))
);


--
-- Name: speaker_match_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.speaker_match_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: speaker_match_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.speaker_match_id_seq OWNED BY public.speaker_match.id;


--
-- Name: speaker_profile; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.speaker_profile (
    id integer NOT NULL,
    user_id integer NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    uuid character varying(255) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: speaker_profile_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.speaker_profile_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: speaker_profile_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.speaker_profile_id_seq OWNED BY public.speaker_profile.id;


--
-- Name: tag; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.tag (
    id integer NOT NULL,
    name character varying(50) NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: tag_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tag_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tag_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tag_id_seq OWNED BY public.tag.id;


--
-- Name: task; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.task (
    id character varying(255) NOT NULL,
    user_id integer NOT NULL,
    media_file_id integer,
    task_type character varying(50) NOT NULL,
    status character varying(50) NOT NULL,
    progress double precision DEFAULT 0.0,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamp with time zone,
    error_message text
);


--
-- Name: transcript_segment; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.transcript_segment (
    id integer NOT NULL,
    media_file_id integer NOT NULL,
    speaker_id integer,
    start_time double precision NOT NULL,
    end_time double precision NOT NULL,
    text text NOT NULL
);


--
-- Name: transcript_segment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.transcript_segment_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: transcript_segment_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.transcript_segment_id_seq OWNED BY public.transcript_segment.id;


--
-- Name: user; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public."user" (
    id integer NOT NULL,
    email character varying(255) NOT NULL,
    hashed_password character varying(255) NOT NULL,
    full_name character varying(255) NOT NULL,
    is_active boolean DEFAULT true NOT NULL,
    is_superuser boolean DEFAULT false NOT NULL,
    role character varying(50) DEFAULT 'user'::character varying,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP
);


--
-- Name: user_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.user_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: user_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.user_id_seq OWNED BY public."user".id;


--
-- Name: analytics id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics ALTER COLUMN id SET DEFAULT nextval('public.analytics_id_seq'::regclass);


--
-- Name: collection id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection ALTER COLUMN id SET DEFAULT nextval('public.collection_id_seq'::regclass);


--
-- Name: collection_member id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_member ALTER COLUMN id SET DEFAULT nextval('public.collection_member_id_seq'::regclass);


--
-- Name: comment id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment ALTER COLUMN id SET DEFAULT nextval('public.comment_id_seq'::regclass);


--
-- Name: file_tag id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_tag ALTER COLUMN id SET DEFAULT nextval('public.file_tag_id_seq'::regclass);


--
-- Name: media_file id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media_file ALTER COLUMN id SET DEFAULT nextval('public.media_file_id_seq'::regclass);


--
-- Name: speaker id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker ALTER COLUMN id SET DEFAULT nextval('public.speaker_id_seq'::regclass);


--
-- Name: speaker_collection id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_collection ALTER COLUMN id SET DEFAULT nextval('public.speaker_collection_id_seq'::regclass);


--
-- Name: speaker_collection_member id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_collection_member ALTER COLUMN id SET DEFAULT nextval('public.speaker_collection_member_id_seq'::regclass);


--
-- Name: speaker_match id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_match ALTER COLUMN id SET DEFAULT nextval('public.speaker_match_id_seq'::regclass);


--
-- Name: speaker_profile id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_profile ALTER COLUMN id SET DEFAULT nextval('public.speaker_profile_id_seq'::regclass);


--
-- Name: tag id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag ALTER COLUMN id SET DEFAULT nextval('public.tag_id_seq'::regclass);


--
-- Name: transcript_segment id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transcript_segment ALTER COLUMN id SET DEFAULT nextval('public.transcript_segment_id_seq'::regclass);


--
-- Name: user id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."user" ALTER COLUMN id SET DEFAULT nextval('public.user_id_seq'::regclass);


--
-- Data for Name: analytics; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.analytics (id, media_file_id, speaker_stats, sentiment, keywords) FROM stdin;
\.


--
-- Data for Name: collection; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.collection (id, name, description, user_id, is_public, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: collection_member; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.collection_member (id, collection_id, media_file_id, added_at) FROM stdin;
\.


--
-- Data for Name: comment; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.comment (id, media_file_id, user_id, text, "timestamp", created_at) FROM stdin;
\.


--
-- Data for Name: file_tag; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.file_tag (id, media_file_id, tag_id, created_at) FROM stdin;
\.


--
-- Data for Name: media_file; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.media_file (id, filename, storage_path, file_size, duration, upload_time, completed_at, content_type, status, is_public, language, summary, translated_text, file_hash, thumbnail_path, metadata_raw, metadata_important, media_format, codec, frame_rate, frame_count, resolution_width, resolution_height, aspect_ratio, audio_channels, audio_sample_rate, audio_bit_depth, creation_date, last_modified_date, device_make, device_model, title, author, description, user_id) FROM stdin;
\.


--
-- Data for Name: speaker; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.speaker (id, user_id, media_file_id, profile_id, name, display_name, suggested_name, uuid, verified, confidence, embedding_vector, created_at) FROM stdin;
\.


--
-- Data for Name: speaker_collection; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.speaker_collection (id, name, description, user_id, is_public, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: speaker_collection_member; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.speaker_collection_member (id, collection_id, speaker_profile_id, added_at) FROM stdin;
\.


--
-- Data for Name: speaker_match; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.speaker_match (id, speaker1_id, speaker2_id, confidence, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: speaker_profile; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.speaker_profile (id, user_id, name, description, uuid, created_at, updated_at) FROM stdin;
\.


--
-- Data for Name: tag; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.tag (id, name, created_at) FROM stdin;
1	Important	2025-06-23 05:48:44.912891+00
2	Meeting	2025-06-23 05:48:44.912891+00
3	Interview	2025-06-23 05:48:44.912891+00
4	Personal	2025-06-23 05:48:44.912891+00
\.


--
-- Data for Name: task; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.task (id, user_id, media_file_id, task_type, status, progress, created_at, updated_at, completed_at, error_message) FROM stdin;
\.


--
-- Data for Name: transcript_segment; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.transcript_segment (id, media_file_id, speaker_id, start_time, end_time, text) FROM stdin;
\.


--
-- Data for Name: user; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public."user" (id, email, hashed_password, full_name, is_active, is_superuser, role, created_at, updated_at) FROM stdin;
1	admin@example.com	$2b$12$8kYjEPgJ1Rr.zu5iDcX.e.ScFMOEsLDS.A1IYXjKlKOxdzeDIjqx6	Admin User	t	t	admin	2025-06-23 05:48:44.534954+00	2025-06-23 05:48:44.534954+00
\.


--
-- Name: analytics_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.analytics_id_seq', 1, false);


--
-- Name: collection_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.collection_id_seq', 1, false);


--
-- Name: collection_member_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.collection_member_id_seq', 1, false);


--
-- Name: comment_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.comment_id_seq', 1, false);


--
-- Name: file_tag_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.file_tag_id_seq', 1, false);


--
-- Name: media_file_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.media_file_id_seq', 1, false);


--
-- Name: speaker_collection_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.speaker_collection_id_seq', 1, false);


--
-- Name: speaker_collection_member_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.speaker_collection_member_id_seq', 1, false);


--
-- Name: speaker_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.speaker_id_seq', 1, false);


--
-- Name: speaker_match_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.speaker_match_id_seq', 1, false);


--
-- Name: speaker_profile_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.speaker_profile_id_seq', 1, false);


--
-- Name: tag_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.tag_id_seq', 4, true);


--
-- Name: transcript_segment_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.transcript_segment_id_seq', 1, false);


--
-- Name: user_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.user_id_seq', 1, true);


--
-- Name: analytics analytics_media_file_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics
    ADD CONSTRAINT analytics_media_file_id_key UNIQUE (media_file_id);


--
-- Name: analytics analytics_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics
    ADD CONSTRAINT analytics_pkey PRIMARY KEY (id);


--
-- Name: collection_member collection_member_collection_id_media_file_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_member
    ADD CONSTRAINT collection_member_collection_id_media_file_id_key UNIQUE (collection_id, media_file_id);


--
-- Name: collection_member collection_member_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_member
    ADD CONSTRAINT collection_member_pkey PRIMARY KEY (id);


--
-- Name: collection collection_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection
    ADD CONSTRAINT collection_pkey PRIMARY KEY (id);


--
-- Name: collection collection_user_id_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection
    ADD CONSTRAINT collection_user_id_name_key UNIQUE (user_id, name);


--
-- Name: comment comment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment
    ADD CONSTRAINT comment_pkey PRIMARY KEY (id);


--
-- Name: file_tag file_tag_media_file_id_tag_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_tag
    ADD CONSTRAINT file_tag_media_file_id_tag_id_key UNIQUE (media_file_id, tag_id);


--
-- Name: file_tag file_tag_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_tag
    ADD CONSTRAINT file_tag_pkey PRIMARY KEY (id);


--
-- Name: media_file media_file_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media_file
    ADD CONSTRAINT media_file_pkey PRIMARY KEY (id);


--
-- Name: speaker_collection_member speaker_collection_member_collection_id_speaker_profile_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_collection_member
    ADD CONSTRAINT speaker_collection_member_collection_id_speaker_profile_id_key UNIQUE (collection_id, speaker_profile_id);


--
-- Name: speaker_collection_member speaker_collection_member_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_collection_member
    ADD CONSTRAINT speaker_collection_member_pkey PRIMARY KEY (id);


--
-- Name: speaker_collection speaker_collection_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_collection
    ADD CONSTRAINT speaker_collection_pkey PRIMARY KEY (id);


--
-- Name: speaker_collection speaker_collection_user_id_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_collection
    ADD CONSTRAINT speaker_collection_user_id_name_key UNIQUE (user_id, name);


--
-- Name: speaker_match speaker_match_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_match
    ADD CONSTRAINT speaker_match_pkey PRIMARY KEY (id);


--
-- Name: speaker_match speaker_match_speaker1_id_speaker2_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_match
    ADD CONSTRAINT speaker_match_speaker1_id_speaker2_id_key UNIQUE (speaker1_id, speaker2_id);


--
-- Name: speaker speaker_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker
    ADD CONSTRAINT speaker_pkey PRIMARY KEY (id);


--
-- Name: speaker_profile speaker_profile_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_profile
    ADD CONSTRAINT speaker_profile_pkey PRIMARY KEY (id);


--
-- Name: speaker_profile speaker_profile_user_id_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_profile
    ADD CONSTRAINT speaker_profile_user_id_name_key UNIQUE (user_id, name);


--
-- Name: speaker_profile speaker_profile_uuid_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_profile
    ADD CONSTRAINT speaker_profile_uuid_key UNIQUE (uuid);


--
-- Name: speaker speaker_user_id_media_file_id_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker
    ADD CONSTRAINT speaker_user_id_media_file_id_name_key UNIQUE (user_id, media_file_id, name);


--
-- Name: tag tag_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag
    ADD CONSTRAINT tag_name_key UNIQUE (name);


--
-- Name: tag tag_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.tag
    ADD CONSTRAINT tag_pkey PRIMARY KEY (id);


--
-- Name: task task_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task
    ADD CONSTRAINT task_pkey PRIMARY KEY (id);


--
-- Name: transcript_segment transcript_segment_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transcript_segment
    ADD CONSTRAINT transcript_segment_pkey PRIMARY KEY (id);


--
-- Name: user user_email_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."user"
    ADD CONSTRAINT user_email_key UNIQUE (email);


--
-- Name: user user_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public."user"
    ADD CONSTRAINT user_pkey PRIMARY KEY (id);


--
-- Name: idx_collection_member_collection_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_collection_member_collection_id ON public.collection_member USING btree (collection_id);


--
-- Name: idx_collection_member_media_file_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_collection_member_media_file_id ON public.collection_member USING btree (media_file_id);


--
-- Name: idx_collection_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_collection_user_id ON public.collection USING btree (user_id);


--
-- Name: idx_media_file_hash; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_media_file_hash ON public.media_file USING btree (file_hash);


--
-- Name: idx_media_file_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_media_file_status ON public.media_file USING btree (status);


--
-- Name: idx_media_file_upload_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_media_file_upload_time ON public.media_file USING btree (upload_time);


--
-- Name: idx_media_file_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_media_file_user_id ON public.media_file USING btree (user_id);


--
-- Name: idx_speaker_collection_member_collection_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_speaker_collection_member_collection_id ON public.speaker_collection_member USING btree (collection_id);


--
-- Name: idx_speaker_collection_member_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_speaker_collection_member_profile_id ON public.speaker_collection_member USING btree (speaker_profile_id);


--
-- Name: idx_speaker_collection_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_speaker_collection_user_id ON public.speaker_collection USING btree (user_id);


--
-- Name: idx_speaker_match_confidence; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_speaker_match_confidence ON public.speaker_match USING btree (confidence);


--
-- Name: idx_speaker_match_speaker1; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_speaker_match_speaker1 ON public.speaker_match USING btree (speaker1_id);


--
-- Name: idx_speaker_match_speaker2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_speaker_match_speaker2 ON public.speaker_match USING btree (speaker2_id);


--
-- Name: idx_speaker_media_file_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_speaker_media_file_id ON public.speaker USING btree (media_file_id);


--
-- Name: idx_speaker_profile_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_speaker_profile_id ON public.speaker USING btree (profile_id);


--
-- Name: idx_speaker_profile_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_speaker_profile_user_id ON public.speaker_profile USING btree (user_id);


--
-- Name: idx_speaker_profile_uuid; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_speaker_profile_uuid ON public.speaker_profile USING btree (uuid);


--
-- Name: idx_speaker_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_speaker_user_id ON public.speaker USING btree (user_id);


--
-- Name: idx_speaker_verified; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_speaker_verified ON public.speaker USING btree (verified);


--
-- Name: idx_task_media_file_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_media_file_id ON public.task USING btree (media_file_id);


--
-- Name: idx_task_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_status ON public.task USING btree (status);


--
-- Name: idx_task_user_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_task_user_id ON public.task USING btree (user_id);


--
-- Name: idx_transcript_segment_media_file_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_transcript_segment_media_file_id ON public.transcript_segment USING btree (media_file_id);


--
-- Name: idx_transcript_segment_speaker_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_transcript_segment_speaker_id ON public.transcript_segment USING btree (speaker_id);


--
-- Name: analytics analytics_media_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.analytics
    ADD CONSTRAINT analytics_media_file_id_fkey FOREIGN KEY (media_file_id) REFERENCES public.media_file(id);


--
-- Name: collection_member collection_member_collection_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_member
    ADD CONSTRAINT collection_member_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES public.collection(id) ON DELETE CASCADE;


--
-- Name: collection_member collection_member_media_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection_member
    ADD CONSTRAINT collection_member_media_file_id_fkey FOREIGN KEY (media_file_id) REFERENCES public.media_file(id) ON DELETE CASCADE;


--
-- Name: collection collection_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collection
    ADD CONSTRAINT collection_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: comment comment_media_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment
    ADD CONSTRAINT comment_media_file_id_fkey FOREIGN KEY (media_file_id) REFERENCES public.media_file(id);


--
-- Name: comment comment_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.comment
    ADD CONSTRAINT comment_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: file_tag file_tag_media_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_tag
    ADD CONSTRAINT file_tag_media_file_id_fkey FOREIGN KEY (media_file_id) REFERENCES public.media_file(id) ON DELETE CASCADE;


--
-- Name: file_tag file_tag_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.file_tag
    ADD CONSTRAINT file_tag_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.tag(id) ON DELETE CASCADE;


--
-- Name: media_file media_file_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.media_file
    ADD CONSTRAINT media_file_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: speaker_collection_member speaker_collection_member_collection_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_collection_member
    ADD CONSTRAINT speaker_collection_member_collection_id_fkey FOREIGN KEY (collection_id) REFERENCES public.speaker_collection(id) ON DELETE CASCADE;


--
-- Name: speaker_collection_member speaker_collection_member_speaker_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_collection_member
    ADD CONSTRAINT speaker_collection_member_speaker_profile_id_fkey FOREIGN KEY (speaker_profile_id) REFERENCES public.speaker_profile(id) ON DELETE CASCADE;


--
-- Name: speaker_collection speaker_collection_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_collection
    ADD CONSTRAINT speaker_collection_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: speaker_match speaker_match_speaker1_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_match
    ADD CONSTRAINT speaker_match_speaker1_id_fkey FOREIGN KEY (speaker1_id) REFERENCES public.speaker(id) ON DELETE CASCADE;


--
-- Name: speaker_match speaker_match_speaker2_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_match
    ADD CONSTRAINT speaker_match_speaker2_id_fkey FOREIGN KEY (speaker2_id) REFERENCES public.speaker(id) ON DELETE CASCADE;


--
-- Name: speaker speaker_media_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker
    ADD CONSTRAINT speaker_media_file_id_fkey FOREIGN KEY (media_file_id) REFERENCES public.media_file(id) ON DELETE CASCADE;


--
-- Name: speaker speaker_profile_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker
    ADD CONSTRAINT speaker_profile_id_fkey FOREIGN KEY (profile_id) REFERENCES public.speaker_profile(id) ON DELETE SET NULL;


--
-- Name: speaker_profile speaker_profile_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker_profile
    ADD CONSTRAINT speaker_profile_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: speaker speaker_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.speaker
    ADD CONSTRAINT speaker_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: task task_media_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task
    ADD CONSTRAINT task_media_file_id_fkey FOREIGN KEY (media_file_id) REFERENCES public.media_file(id);


--
-- Name: task task_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.task
    ADD CONSTRAINT task_user_id_fkey FOREIGN KEY (user_id) REFERENCES public."user"(id);


--
-- Name: transcript_segment transcript_segment_media_file_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transcript_segment
    ADD CONSTRAINT transcript_segment_media_file_id_fkey FOREIGN KEY (media_file_id) REFERENCES public.media_file(id);


--
-- Name: transcript_segment transcript_segment_speaker_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transcript_segment
    ADD CONSTRAINT transcript_segment_speaker_id_fkey FOREIGN KEY (speaker_id) REFERENCES public.speaker(id);


--
-- PostgreSQL database dump complete
--


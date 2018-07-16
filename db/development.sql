COPY account (id, created_at, is_staff, facebook_id, email, full_name, access_token, tz, banned_at, profile) FROM stdin;
1	2013-09-11 02:07:45.341189-04	f	423180	toc3@cornell.edu	Trevor Caira	pighetiemeinirahnobeichahliequah	America/New_York	\N	https://fbcdn-profile-a.akamaihd.net/hprofile-ak-prn2/187054_423180_5002717_q.jpg
2	2013-09-11 21:42:31.84654-04	f	100004759357635	mgoldberg@zaznu.me	Marty Goldberg	oabozeibaengeimahphaipieloosahzu	America/New_York	\N	\N
\.
SELECT pg_catalog.setval('account_id_seq', 2, true);

COPY city (id, name, location) FROM stdin;
1	New York	0101000020E6100000CCF09F6EA07F52C07DCC07043A5D4440
2	Austin	0101000020E61000009087BEBB956F58C0A164726A67443E40
\.
SELECT pg_catalog.setval('city_id_seq', 2, true);

REFRESH MATERIALIZED VIEW venue_city;

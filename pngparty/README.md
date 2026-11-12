# PNG Party: Member Platform & Offline Field PWA

Steps 1 to 4 of the spec: project skeleton, member models + batch sync API,
offline field-agent PWA, WeasyPrint ID cards. The public website (Module A)
is stubbed in `apps/cms` for the next step.

## Structure

```
pngparty/
├── manage.py
├── requirements.txt
├── .env.example
├── config/                      settings.py · urls.py · wsgi.py
├── apps/
│   ├── geo/                     Province, Electorate, lookup API, seed_provinces command
│   ├── accounts/                custom User (role, assigned province/electorate)
│   ├── members/
│   │   ├── models.py            Member, SyncLog
│   │   ├── serializers.py       MemberSyncSerializer, MemberSerializer
│   │   ├── views.py             BatchSyncView, MemberViewSet, card PDFs, /verify/
│   │   ├── permissions.py       RBAC scoping (members_visible_to)
│   │   ├── utils.py             phone/NID normalisation, server-side photo re-encode
│   │   ├── idcards.py           WeasyPrint rendering + QR + A4 layout maths
│   │   ├── admin.py             interim coordinator portal (verify / print actions)
│   │   └── templates/members/   _card.html · _card_styles.html · idcard_single.html
│   │                            idcard_batch.html · verify.html
│   ├── cms/                     NewsPost, PolicyDocument (public site next)
│   └── pwa/                     serves /agent/, /agent/sw.js, manifest
│       └── templates/pwa/       index.html · sw.js · manifest.webmanifest
└── static/pwa/
    ├── js/                      db.js · sync.js · app.js
    ├── vendor/                  dexie.min.js (download, see README there)
    └── icons/                   placeholder icons; replace with party logo
```

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
sudo apt install libpango-1.0-0 libpangoft2-1.0-0 fonts-dejavu   # WeasyPrint
cp .env.example .env   # then export the vars (or use your process manager)
curl -L -o static/pwa/vendor/dexie.min.js https://unpkg.com/dexie@4/dist/dexie.min.js
python manage.py makemigrations geo accounts members cms
python manage.py migrate
python manage.py seed_provinces
python manage.py createsuperuser
python manage.py runserver
```

Field agents open `/agent/` (needs HTTPS in production for camera, service
worker and `crypto.randomUUID`). Coordinators use `/admin/` for now.

## Sync contract

`POST /api/members/sync/` (Bearer JWT, multipart):
- `records`: JSON array, max 10, each with client UUID `id`
- `photo_<id>`: image file per record (optional)

Response `200 {results:[{id,status,...}], summary:{...}}` with status per record:

| status | meaning | client action |
|---|---|---|
| `created` | stored | strip PII, mark sent |
| `already_synced` | UUID already on server (retry after a lost reply) | same |
| `flagged` | stored, linked as possible duplicate for coordinator review | same |
| `rejected` | validation failed (`errors` given) | keep, agent fixes and resends with same UUID |

Duplicates are never thrown away: a matching NID (or same name and phone) is
stored with `duplicate_of` set so a coordinator decides. A shared phone alone
is only a soft flag, since families often share one handset.

## Other endpoints

- `POST /api/auth/token/` · `POST /api/auth/token/refresh/`
- `GET  /api/geo/electorates/`: lookup the PWA caches
- `GET  /api/members/sync/history/`: agent's own batches
- `GET/PATCH /api/members/records/` · `POST .../<id>/verify/` · `POST .../<id>/clear-flag/`
- `GET  /portal/members/<id>/card.pdf`: single CR80
- `POST /portal/members/cards.pdf`: `ids=…` or `unprinted=1`, `per_page=8|10`
- `GET  /verify/<uuid>/`: public QR target (name, number, electorate only)

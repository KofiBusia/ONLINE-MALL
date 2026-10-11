# Edwom Online Mall

Ghana's online mall for small businesses. Buyers walk through a directory of shops, buy from several
shops in one checkout and pay by Mobile Money, card or on delivery. Edwom holds the money and releases it
to each shop only when the buyer confirms delivery, or automatically 72 hours after delivery.

Python 3.12, Flask, SQLAlchemy, PostgreSQL. Deploys to Render from GitHub. Payments run in demo mode
until a Paystack key is added.

## Who does what

| Role | How they get in | What they can do |
|---|---|---|
| **Super admin** | Created from `ADMIN_EMAIL` / `ADMIN_PASSWORD` at deploy | Create shops and their owner logins; upload logos, banners and product photos for **any** shop; verify or suspend shops; reset owner passwords; review applications; resolve buyer disputes; see all orders and the activity log |
| **Shop owner** | Login created by the super admin. The temporary password must be changed at first login | Upload product photos (up to 8 per product, choose the cover) with full details: price, old price for discounts, stock, SKU, description, specifications, draft or live. Logo and banner, order fulfilment, money held, paid out and commission |
| **Buyer** | Optional account; guest checkout allowed | Browse shops and products, cart across shops, checkout, track orders, confirm delivery, report problems |
| **Applicant** | Public "Sell on Edwom" form | Apply to sell; the super admin approves and the new-shop form is prefilled from the application |

## Photos

- JPG, PNG or WebP, up to 10 MB each, up to 8 per product. iPhone HEIC photos need to be shared as JPG
  (most phones do this automatically when uploading through a browser).
- Every upload is checked, turned the right way up, stripped of location data, resized (1600 px and
  640 px) and converted to WebP, usually 60 to 250 KB each.
- Images are stored **in the PostgreSQL database**, so they survive Render restarts and redeploys
  (Render wipes its disk on every deploy). Browsers cache them for a year.
- A product can't go live without a photo, but it can be saved as a draft.
- At large scale (thousands of products), move images to Cloudinary or S3. Only `edwom/media.py` and the
  `/media` route need to change.

## Production features

- Database migrations (Alembic) applied automatically on every deploy.
- CSRF protection on every form, hashed passwords with a minimum strength, and a forced password change
  for logins created by the admin.
- Rate limits on login, sign-up, applications and order tracking.
- Strict security headers (Content Security Policy, HSTS, frame blocking) and secure cookies.
- Suspending a shop hides it and locks the owner out immediately.
- Audit log of every admin and shop-owner change.
- Pagination, a health check that pings the database, and friendly 404, 413, 429 and 500 pages.
- 13 automated end-to-end tests, also run by GitHub on every push (`.github/workflows/tests.yml`).
- Gunicorn configuration tuned for Render.

## 1. Run it on your computer

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # then set ADMIN_EMAIL and ADMIN_PASSWORD
flask --app wsgi db upgrade       # creates the tables
flask --app wsgi setup            # creates the super admin and the demo shops
flask --app wsgi run --debug
```

Open http://127.0.0.1:5000 and log in with your admin email; you land on the admin dashboard.
Run the tests with `python -m pytest`.

## 2. Put it on GitHub

1. Create a **private** repository on github.com, for example `edwom-online-mall`.
2. Upload everything inside this folder and keep the structure, including the hidden `.github`
   folder and the `.gitignore` file, plus the `migrations` folder. With Git:
   ```bash
   git init && git add . && git commit -m "Edwom Online Mall"
   git branch -M main
   git remote add origin https://github.com/YOUR-USERNAME/edwom-online-mall.git
   git push -u origin main
   ```

## 3. Deploy on Render

1. Sign in at render.com with GitHub. Choose **New → Blueprint** and pick the repository.
2. Render reads `render.yaml` and creates the web service and the PostgreSQL database.
3. Enter `ADMIN_EMAIL` and a strong `ADMIN_PASSWORD` (10+ characters, letters and numbers).
   Leave `PAYSTACK_SECRET_KEY` empty for demo payments.
4. Click **Apply**. Every start runs the migrations, makes sure the super admin exists, then starts
   the web server.
5. Open your site, log in, and go to **Admin → New shop**.

Every push to `main` redeploys automatically.

**Before real customers:** move the web service and the database to paid Render plans. Free web services
sleep when idle and free databases are time-limited (check Render's current terms). Then set
`SEED_DEMO=0` and suspend the demo shops from the admin page.

## Setting up a shop (super admin)

1. **Admin → New shop**: enter the shop details, the owner's name and email, and optionally a logo and banner.
2. The next screen shows a **temporary password once**. Send it to the owner privately.
3. Add products yourself (**Add the first product**), or let the owner log in, set their own password
   and upload their own products and photos.
4. Tick **Verified business** after checking their Ghana Card and business registration.
5. If an owner forgets their password, go to **Shops → Manage → Reset password**.

## Settings

| Variable | Default | Meaning |
|---|---|---|
| `SECRET_KEY` | generated by Render | Signs sessions. Required in production |
| `DATABASE_URL` | set by Render | PostgreSQL. Empty locally means SQLite |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | | Super admin login |
| `SEED_DEMO` | `1` | Load demo shops when there are none |
| `PAYSTACK_SECRET_KEY` | empty | Empty means demo payments |
| `COMMISSION_RATE` | `0.08` | Commission on completed sales |
| `DELIVERY_SAME_REGION_PESEWAS` / `DELIVERY_OTHER_REGION_PESEWAS` | `2500` / `4500` | Delivery fee per shop (GH₵25 / GH₵45) |
| `AUTO_RELEASE_HOURS` | `72` | Hours after delivery before the shop is paid automatically |
| `MAX_PHOTOS_PER_PRODUCT` / `MAX_PHOTO_MB` | `8` / `10` | Photo limits |
| `RATELIMIT_STORAGE_URI` | `memory://` | Use a Redis URL when running more than one instance |

## Changing the database later

After editing `edwom/models.py`, create a migration and commit it:

```bash
flask --app wsgi db migrate -m "describe the change"
flask --app wsgi db upgrade
```

Render applies it automatically on the next deploy.

## Project layout

```
wsgi.py               Entry point
gunicorn.conf.py      Web server settings
render.yaml           Render Blueprint (web service + PostgreSQL)
migrations/           Database migrations
tests/                Automated tests
edwom/
  models.py           Users, shops, products, photos, applications, orders, audit log
  media.py            Photo checks, resizing and WebP conversion
  catalog.py          Saving products and shop images (used by owners and admin)
  services.py         Cart, delivery fees, checkout, escrow release, search
  security.py         Security headers and forced password change
  routes/             main (buyers), auth, seller (shop owners), admin (super admin)
  templates/          Pages
  static/             Styles and scripts
```

## Going live checklist

- Paid Render plans, `SEED_DEMO=0`, demo shops suspended, a custom domain (e.g. `edwom.com.gh`).
- Register with the Data Protection Commission (Ghana Card numbers are personal data) and publish
  buyer terms, seller terms, a refund policy and a privacy notice.
- Agree rider and courier rates and set the delivery fees.
- For real money: a Paystack account, `PAYSTACK_SECRET_KEY`, and the webhook URL
  `https://YOUR-SITE/payment/webhook` in the Paystack dashboard.

## Roadmap

SMS order updates (Hubtel, mNotify), emailing shop logins automatically, automatic MoMo payouts
(Paystack Transfers), ratings and reviews, mall wings by category, and a CDN for images at scale.

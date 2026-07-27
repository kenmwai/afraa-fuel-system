# System Maintenance and Operations Guide

This guide details the maintenance, local development, database operations, and deployment procedures for the **AFRAA Fuel Procurement System**.

---

## 1. Local Development Setup

To run the application locally on your machine for debugging or implementing new features:

### Step 1: Activate the Virtual Environment
Navigate to the root directory and activate the virtualenv:
*   **Windows (PowerShell):**
    ```powershell
    venv\Scripts\Activate.ps1
    ```
*   **Windows (CMD):**
    ```cmd
    venv\Scripts\activate.bat
    ```
*   **macOS/Linux:**
    ```bash
    source venv/bin/activate
    ```

### Step 2: Install Dependencies
If you add any new packages, make sure they are installed and updated in the environment:
```bash
pip install -r requirements.txt
```

### Step 3: Run the Local Server
Start Django's development server:
```bash
python manage.py runserver
```
The application will be accessible at: `http://127.0.0.1:8000/`.

> [!NOTE]
> During local development, the app will automatically fall back to using the local SQLite database (`db.sqlite3`) and will have `DEBUG = True` by default.

---

## 2. Database Management & Migrations

The production database is hosted on **Neon PostgreSQL**. Because Vercel's serverless hosting is ephemeral and read-only, all database schema updates (migrations) must be run from your local terminal.

### Running Migrations on Production
When you make changes to database models in `procurement/models.py`:

1.  **Generate Migration Files locally:**
    ```bash
    python manage.py makemigrations
    ```
2.  **Commit and push the new migration files to Git** (so Vercel has the updated code structures):
    ```bash
    git add .
    git commit -m "Create migrations for [feature name]"
    git push
    ```
3.  **Apply Migrations to the Production Neon Database:**
    Set the `DATABASE_URL` environment variable temporarily in your terminal session, then run the migrate command:
    *   **PowerShell:**
        ```powershell
        $env:DATABASE_URL="your-neon-connection-string"
        python manage.py migrate
        ```
    *   **CMD:**
        ```cmd
        set DATABASE_URL=your-neon-connection-string
        python manage.py migrate
        ```

### Creating Production Superusers (Admins)
If you ever need to create another admin account directly in the production database:
1.  Connect your terminal to the production database:
    ```powershell
    $env:DATABASE_URL="your-neon-connection-string"
    ```
2.  Run the Django createsuperuser command:
    ```bash
    python manage.py createsuperuser
    ```
3.  Follow the prompts to enter a username, email, and password.

---

## 3. Deployment Workflow

Deployments are fully automated via GitHub integration.

1.  Commit your work:
    ```bash
    git add .
    git commit -m "Describe your changes"
    ```
2.  Push to the main branch:
    ```bash
    git push origin main
    ```
3.  Vercel will detect the push to `main` and automatically:
    *   Initialize the build container.
    *   Install python requirements from `requirements.txt`.
    *   Automatically run `python manage.py collectstatic --noinput` to compile CSS/JS.
    *   Expose WSGI endpoints through Serverless Functions.
    *   Publish static files to the Vercel CDN.

---

## 4. Environment Variables Checklist

The following environment variables must be configured in the **Vercel Dashboard** under **Project Settings > Environment Variables**:

| Variable Name | Description | Value Example / Reference |
| :--- | :--- | :--- |
| `DJANGO_SECRET_KEY` | Encryption key for session signing and security hashes. | Generated random long string. |
| `DJANGO_DEBUG` | Disables verbose debug pages in production. | Set to `False` (defaults to `True` if omitted). |
| `DATABASE_URL` | Neon PostgreSQL production database connection string. | `postgresql://user:pass@host/db?sslmode=require` |
| `VERCEL_URL` | Automatically populated by Vercel; used for CORS/CSRF. | E.g. `afraa-fuel-system.vercel.app` |

---

## 5. Media Files (Uploaded Documents)

The system allows suppliers to upload files (e.g. business registration, insurance certificates).
*   **Current State:** Uploaded files are handled via Django's default filesystem backend and saved to the `media/` directory.
*   **Serverless Warning:** In a serverless environment like Vercel, files saved to `media/` will be deleted whenever the serverless container spins down.
*   **Recommended Action:** If you notice that supplier verification uploads are disappearing over time, you should configure a cloud storage provider (such as Amazon S3, Azure Blob, or Cloudinary). This is achieved using the `django-storages` package and adding the respective keys to your environment variables.

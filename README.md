# Kubera Fullstack Application

Kubera is a comprehensive multi-tenant platform featuring DocVault, AuditEase, SecretarialEase, ROC Compliance, and an admin portal for managing company operations and compliances.

This project uses **FastAPI (async)** on the backend with **PostgreSQL**, **Redis**, and **Celery**, and **React + Vite** with **Tailwind CSS** on the frontend.

---

## 🚀 Deployment Prerequisites (Linux Distros)

To deploy Kubera, you need Docker, Docker Compose (v2+), Node.js, and Git. Here are the commands to install these dependencies on various Linux distributions.

### Ubuntu / Debian
```bash
# Update and install basic tools
sudo apt update && sudo apt install -y git curl npm

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Node Version Manager (NVM) & Node.js
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.5/install.sh | bash
source ~/.bashrc
nvm install 20
```

### CentOS / RHEL / Fedora
```bash
# Install git and npm
sudo dnf install -y git curl npm

# Install Docker
sudo dnf config-manager --add-repo=https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo systemctl enable --now docker
sudo usermod -aG docker $USER

# Install Node Version Manager (NVM) & Node.js
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.5/install.sh | bash
source ~/.bashrc
nvm install 20
```

### Arch Linux
```bash
sudo pacman -Syu
sudo pacman -S git docker docker-compose npm nodejs

sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```
*(Note: Log out and log back in to apply the `docker` group changes before running the app).*

---

## 🛠 Setting up `.env` and Keys

1. Clone the repository and go to the directory:
   ```bash
   git clone https://github.com/arnav-hiwarkar/new_kubera && cd new_kubera
   ```

2. Create your `.env` file from the example:
   ```bash
   cp .env.example .env
   ```

3. Generate secure keys and update your `.env` file with them:
   - **`JWT_SECRET_KEY`**: Run `openssl rand -hex 32` to generate a random 64-character string.
   - **`ROOT_MASTER_KEK`**: Must be a 32-byte hex string (64 characters). Generate with: 
     ```bash
     python3 -c "import secrets; print(secrets.token_hex(32))"
     ```
   - **`INTERNAL_API_KEY`**: Set this to a long random secret string. This key acts as the root password to create new companies/admins in the platform.

Your resulting `.env` file should look something like this:
```env
# === Database ===
POSTGRES_USER=kubera
POSTGRES_PASSWORD=your_secure_db_password
POSTGRES_DB=kubera
DATABASE_URL=postgresql+asyncpg://kubera:your_secure_db_password@postgres:5432/kubera

# === Redis ===
REDIS_URL=redis://redis:6379/0

# === Auth ===
JWT_SECRET_KEY=e8354c...
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
REFRESH_TOKEN_EXPIRE_DAYS=7

# === Encryption ===
ROOT_MASTER_KEK=f92a34...

# === Internal API ===
INTERNAL_API_KEY=my-super-secret-key-123
```

---

## 🚀 Running the Stack (Deployment)

Kubera is split into a **Backend** (Dockerized) and a **Frontend** (Vite app).

### 1. Start the Backend Infrastructure
The backend uses Docker Compose to orchestrate FastAPI, PostgreSQL, and Redis. Database migrations will run automatically on startup.
```bash
# Start all containers in the background (migrations will run automatically)
docker compose up -d --build
```

### 2. Start the Frontend
In a new terminal window or screen/tmux session:
```bash
cd frontend
npm install
npm run build
npm run preview
# OR for development: npm run dev
```

---

## 🏢 Creating New Companies and Admins

Since Kubera is a multi-tenant platform, standard users cannot register their own companies. Companies and their root administrators must be created using the `INTERNAL_API_KEY` via the internal API endpoint.

You can use `curl` to create a new company and admin account:

```bash
curl -X POST http://localhost:8000/api/v1/auth/companies \
  -H "Content-Type: application/json" \
  -H "x-internal-api-key: <YOUR_INTERNAL_API_KEY_FROM_ENV>" \
  -d '{
    "name": "Acme Corp",
    "admin": {
      "email": "admin@acme.com",
      "password": "SecurePassword123!"
    }
  }'
```

**Response:**
```json
{
  "company": {
    "id": "uuid-here",
    "name": "Acme Corp"
  },
  "admin": {
    "id": "uuid-here",
    "company_id": "uuid-here",
    "email": "admin@acme.com",
    "role": "admin",
    "full_name": "Unknown",
    "is_active": true
  }
}
```

Once the company is created, the admin can log in via the frontend (`/login`) using the credentials specified above. From the frontend Dashboard, the Admin can navigate to the **Directory** and click **Add User** to provision more employees and managers, controlling which modules they have access to via the Module Access toggles.

---

## 📖 API Documentation

Once the backend is running, the interactive API documentation is available at:
- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`

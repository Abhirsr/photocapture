# Face Matcher Admin Portal

A modern Flask-based web application for face matching, with a secure admin portal for managing gallery images, Google Drive integration, admin users, and user activity logs. The admin backend uses Supabase for authentication and logging.

---

## Features

- **User Frontend**
  - Upload and match face images.
  - Submit email to receive results.
  - Clean, responsive UI.

- **Admin Portal**
  - Secure login/logout (Supabase-based).
  - Dashboard with glassmorphism UI.
  - Google Drive link upload for gallery images.
  - Upload Google Drive API credentials.
  - Manage gallery images (delete all).
  - Admin management (add, edit, delete admins).
  - View user activity logs (with search/filter).
  - All admin/user actions logged in Supabase.
  - Session management and access control.

---

## Project Structure

```
matam/
├── app.py                  # Main Flask backend
├── templates/
│   ├── index.html          # User-facing frontend
│   ├── admin_dashboard.html# Admin dashboard UI
│   └── admin_login.html    # Admin login page
├── static/
│   ├── styles.css          # Shared styles
│   └── gallery/            # Uploaded gallery images
├── drive_utils.py          # Google Drive integration
├── requirements.txt        # Python dependencies
└── README.md               # This file
```

---

## Setup Instructions

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd <your-repo-folder>
```

### 2. Install Python Dependencies

It’s recommended to use a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Variables

Create a `.env` file in the root directory with the following (fill in your values):

```
SECRET_KEY=your_flask_secret_key
SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_service_role_key
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your_email@example.com
MAIL_PASSWORD=your_email_password
```

### 4. Supabase Setup

- Create a Supabase project.
- Create the following tables:
  - `admins` (id, username, password_hash, email, created_at)
  - `user_logs` (id, email, ip_address, created_at)
- Set up Row Level Security (RLS) as needed.
- Insert your initial admin user (see code comments in `app.py`).

### 5. Google Drive API

- Place your `credentials.json` in the project root, or upload via the admin dashboard.

---

## Running the App

```bash
python app.py
```

- Visit [http://127.0.0.1:5000/](http://127.0.0.1:5000/) for the user frontend.
- Visit [http://127.0.0.1:5000/admin/login?show=1](http://127.0.0.1:5000/admin/login?show=1) for the admin portal.

---

## Usage

- **User:** Upload a face image, submit your email, and receive results.
- **Admin:** Log in, manage gallery, upload Drive links/credentials, manage admins, and view user logs.

---

## Security Notes

- All admin authentication and logs are stored in Supabase.
- Passwords are hashed with bcrypt.
- Only admins can access the dashboard and sensitive routes.
- User actions are logged for auditing.
- **IMPORTANT:** You must set a strong, random `SECRET_KEY` in your `.env` file or environment variables. If `SECRET_KEY` is missing, Flask sessions will not be secure and you may see warnings or errors. Example:
  ```
  SECRET_KEY=your-very-strong-random-string
  ```

---

## Customization

- Update styles in `

---

## Particle.js Animation Config

To customize the animated background, edit the file at `static/particles.json`. Here is the default config:

```json
{
    "particles": {
      "number": {
        "value": 20,
        "density": {
          "enable": true,
          "value_area": 800
        }
      },
      "color": {
        "value": "#ffffff"
      },
      "shape": {
        "type": "circle",
        "stroke": {
          "width": 0,
          "color": "#000000"
        },
        "polygon": {
          "nb_sides": 4
        },
        "image": {
          "src": "img/github.svg",
          "width": 100,
          "height": 100
        }
      },
      "opacity": {
        "value": 0.5,
        "random": false,
        "anim": {
          "enable": false,
          "speed": 1,
          "opacity_min": 0.1,
          "sync": false
        }
      },
      "size": {
        "value": 10,
        "random": true,
        "anim": {
          "enable": false,
          "speed": 80,
          "size_min": 0.1,
          "sync": false
        }
      },
      "line_linked": {
        "enable": true,
        "distance": 300,
        "color": "#ffffff",
        "opacity": 0.4,
        "width": 2
      },
      "move": {
        "enable": true,
        "speed": 7,
        "direction": "none",
        "random": false,
        "straight": false,
        "out_mode": "out",
        "bounce": false,
        "attract": {
          "enable": false,
          "rotateX": 600,
          "rotateY": 1200
        }
      }
    },
    "interactivity": {
      "detect_on": "canvas",
      "events": {
        "onhover": {
          "enable": false,
          "mode": "repulse"
        },
        "onclick": {
          "enable": true,
          "mode": "push"
        },
        "resize": true
      },
      "modes": {
        "grab": {
          "distance": 800,
          "line_linked": {
            "opacity": 1
          }
        },
        "bubble": {
          "distance": 800,
          "size": 80,
          "duration": 2,
          "opacity": 0.8,
          "speed": 2
        },
        "repulse": {
          "distance": 400,
          "duration": 0.4
        },
        "push": {
          "particles_nb": 4
        },
        "remove": {
          "particles_nb": 2
        }
      }
    },
    "retina_detect": true
  }
```
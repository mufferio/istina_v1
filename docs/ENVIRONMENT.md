# Environment Variables

This project uses environment variables to configure external services such as Supabase.

---

## 🖥️ Frontend

The frontend uses Supabase for authentication and possibly data access.  
To connect to your Supabase project, define the following variables:
- VITE_SUPABASE_URL=your-project-url
- VITE_SUPABASE_ANON_KEY=your-anon-key
---

---

### 📌 Variable Details

#### `VITE_SUPABASE_URL`

- The base URL of your Supabase project.
- Format: 
  - `https://<your-project-id>.supabase.co`


- Found in:
  - **Supabase Dashboard → Project Settings → API → Project URL**


#### `VITE_SUPABASE_ANON_KEY`

- The public **anonymous key** used by the frontend.
- Safe to expose in the browser.
- Used for:
  - user authentication (sign in / sign up)
  - accessing data protected by Row Level Security (RLS)

- Found in:
  - **Supabase Dashboard → Project Settings → API → anon public key**

---

### ⚠️ Important Notes

- Variables **must start with `VITE_`** to be accessible in a Vite app.
- These values are **embedded into the frontend build** and visible to users.

#### Security

- ✅ `VITE_SUPABASE_ANON_KEY` is safe  
- ❌ Do NOT include secrets in frontend environment variables

Never expose:

- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWT_SECRET`
- Any private API keys

---

### 🛠️ Usage in Code

```ts
const supabaseUrl = import.meta.env.VITE_SUPABASE_URL;
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY;
```

---

### 📁 Example `frontend/.env`
```text
VITE_SUPABASE_URL=https://<your-project-id>.supabase.co
VITE_SUPABASE_ANON_KEY=<your-anon-key>
```

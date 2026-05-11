import express from 'express';
import crypto from 'crypto';

const app = express();
app.use(express.json());

// In-memory store (replace with DB in production)
const users = new Map();

// POST /api/v1/users — Create a new user
app.post('/api/v1/users', (req, res) => {
  const { name, email, password } = req.body;

  // Validate required fields
  if (!name || !email || !password) {
    return res.status(400).json({
      error: 'Bad Request',
      message: 'name, email, and password are required',
      statusCode: 400,
    });
  }

  // Check duplicate email
  for (const user of users.values()) {
    if (user.email === email) {
      return res.status(409).json({
        error: 'Conflict',
        message: 'A user with this email already exists',
        statusCode: 409,
      });
    }
  }

  const id = crypto.randomUUID();
  const now = new Date().toISOString();
  const user = { id, name, email, created_at: now, updated_at: now };

  users.set(id, { ...user, password });

  // Never return password
  res.status(201).json(user);
});

// GET /api/v1/users — List users (paginated)
app.get('/api/v1/users', (req, res) => {
  const page = Math.max(1, parseInt(req.query.page) || 1);
  const limit = Math.min(100, Math.max(1, parseInt(req.query.limit) || 20));
  const all = [...users.values()].map(({ password, ...u }) => u);
  const start = (page - 1) * limit;

  res.json({
    data: all.slice(start, start + limit),
    total: all.length,
    page,
    limit,
  });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Listening on :${PORT}`));

# LionFlow AI — API REST

Base URL : `http://localhost:5000/api`

## Authentification

Toutes les routes (sauf `/auth/register` et `/auth/login`) exigent un JWT
dans l'en-tête `Authorization: Bearer <token>`.

### POST /auth/register

Créer un compte.

```json
{
  "email": "user@exemple.com",
  "password": "Password123",
  "first_name": "Jean",
  "last_name": "Dupont"
}
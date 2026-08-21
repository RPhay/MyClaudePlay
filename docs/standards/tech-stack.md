# Technology Stack

This document outlines the baseline technology stack for new projects. This is a generic template for Node.js/Express applications with database support.

## Backend

- **Runtime**: Node.js v20+
- **Framework**: Express.js (v4.18+)
- **Module System**: ES modules (`"type": "module"` in package.json)
- **Templating**: EJS (v3.1+) for server-side rendering

## Database

- **MySQL** (mysql2 v3.6+) — relational database

## Frontend

- **Language**: Vanilla JavaScript or modern framework (React, Vue, Svelte optional)
- **Styling**: CSS (no preprocessor by default)
- **Build**: Optional static asset bundling

## Key Dependencies

### Security & Session Management
- **express-session** (v1.17+) — session middleware
- **csurf** (v1.11+) — CSRF protection
- **helmet** (v7.1+) — HTTP headers security
- **express-validator** (v7.0+) — input validation
- **express-rate-limit** (v7.1+) — rate limiting

### Data Processing & Export
- **csv-writer** (v1.6+) — CSV export
- **exceljs** (v4.3+) — Excel file generation
- **pdfkit** (v0.13+) — PDF generation
- **date-fns** (v2.30+) — date utilities

### HTTP & Communication
- **axios** (v1.19+) — HTTP client

### Logging & Utilities
- **winston** (v3.11+) — structured logging
- **uuid** (v9.0+) — unique ID generation
- **dotenv** (v16.3+) — environment configuration
- **morgan** (v1.10+) — HTTP request logging

## Development & Testing

### Testing
- **Jest** (v29.0+) — unit testing framework
- **Supertest** (v6.3+) — HTTP assertion library
- **Playwright** (v1.62+) — end-to-end testing

### Code Quality
- **ESLint** (v8.50+) — linting
- **Prettier** (v3.0+) — code formatting
- **Nodemon** (v3.0+) — development server with auto-reload

## Project Structure

Recommended structure for service-oriented architecture:

```
src/
  ├── database/          — schema definitions, migrations
  ├── services/          — business logic, domain services
  ├── routes/            — API endpoints
  ├── middleware/        — Express middleware
  ├── public/            — frontend assets (js, css, images)
  │   ├── js/
  │   ├── css/
  │   └── images/
  └── utils/             — utilities, helpers, constants

scripts/                 — database setup, migrations, seeding
tests/                   — unit and integration tests
```

## Key Architectural Patterns

- **Service-Oriented**: Business logic in services, routes delegate to services
- **Centralized Error Handling**: Consistent error responses across all endpoints
- **Centralized Authentication**: Session-based auth with CSRF protection
- **Single Source of Truth**: Configuration, schema, and validation defined once
- **Data-Driven Rendering**: Dynamic templates based on database configuration (optional pattern, see [[uix]] for reference)

## Common Scripts

```bash
npm run start              # Run production server
npm run dev               # Run dev server with auto-reload (nodemon)
npm run db:init           # Initialize database schema
npm run db:migrate        # Run database migrations
npm run db:seed           # Seed initial data
npm run test              # Run all tests
npm run test:watch        # Run tests in watch mode
npm run lint              # Run ESLint
npm run format            # Format code with Prettier
```

Adapt these to your project's specific needs.

## Environment Requirements

- Node.js 20+
- MySQL 5.7+
- Environment variables configured via `.env` file (see .env.example for template)

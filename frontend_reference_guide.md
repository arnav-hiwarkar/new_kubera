# Kubera V1 Frontend Reference Guide

This document serves as a comprehensive guide for the frontend team to build the React application for Kubera V1. It outlines the architectural concepts, data models, API endpoints, and integration patterns required to interface with the FastAPI backend.

---

## 1. High-Level Concepts

### 1.1 Tenant Isolation
The system is fundamentally designed around a multi-tenant architecture. Every record belonging to a company (users, assets, sales, etc.) is strictly isolated by a `company_id`. 
* **Actionable for Frontend:** You do not need to explicitly pass `company_id` in your API payloads. The backend automatically infers it from the JWT token of the logged-in user.

### 1.2 Authentication
The backend uses **JWT Bearer Tokens**.
* **Flow:** On successful login, the frontend receives an `access_token` and `refresh_token`.
* **Usage:** Pass the access token in the headers of all authenticated requests: `Authorization: Bearer <access_token>`.
* **Storage:** Store tokens securely in memory or `localStorage`/`sessionStorage` depending on your security posture.

### 1.3 Roles & Hierarchy
There are three user roles:
* `admin`: Complete access to all company data. Can configure settings, create users, and manage custom fields.
* `manager`: Can manage their own data and the data of users directly reporting to them (via `manager_id`).
* `employee`: Can only view and manage their own assigned data.

---

## 2. Core Modules & Endpoints

Base URL: `http://localhost:8000/api/v1` (or respective environment URL).

### 2.1 Authentication (`/auth`)

* `POST /company/login`: Authenticates a user.
  * **Payload:** `{ "email": "user@test.com", "password": "password" }`
  * **Response:** `{ "access_token": "...", "refresh_token": "...", "token_type": "bearer", "role": "admin", "full_name": "Ash" }`
* `POST /company/refresh`: Refreshes an expired access token.
* `POST /company`: (Admin only/Internal) Registers a new company and its root admin.

### 2.2 User Management (`/users`)

Manages the employee directory and hierarchy.
* **Schema Highlights:** `email`, `full_name`, `role` (admin/manager/employee), `manager_id` (UUID), `designation`, `department`, `is_active`.
* `GET /users`: List all users (Admin only).
* `POST /users`: Create a new user (Admin only).
* `GET /users/me`: Get current logged-in user details.
* `GET /users/me/reports`: Get users directly reporting to the current logged-in manager (Manager/Admin only).
* `GET /users/{id}`: Get specific user details.
* `PATCH /users/{id}`: Update user (designation, department, manager transfer).
* `PATCH /users/{id}/deactivate`: Soft-delete a user.

### 2.3 Custom Fields (`/custom-fields/{module}`)

Dynamic fields that admins can configure for different modules (`asset_management`, `sales_tracking`).
* **Schema Highlights:** `field_name`, `field_key` (slugified), `field_type` (`text`, `number`, `date`, `dropdown`), `is_required`, `dropdown_options` (array of strings), `display_order`.
* `GET /custom-fields/{module}`: Lists active custom fields for the module. **Frontend should call this to dynamically generate form inputs.**
* `POST /custom-fields/{module}`: Create a new custom field (Admin only).
* `PATCH /custom-fields/{module}/{id}`: Update field settings.
* `PATCH /custom-fields/{module}/{id}/deactivate`: Hide a field from forms (doesn't delete existing data).

### 2.4 Asset Management (`/assets`)

Tracks physical and digital assets within the company.
* **Schema Highlights:** `asset_name`, `serial_number`, `category` (`hardware`, `software`, `furniture`, `vehicle`, `other`), `status` (`active`, `maintenance`, `retired`), `purchase_cost`, `custodian_id` (assigned user).
* `GET /assets`: List assets.
  * *Query Params:* `category`, `status`.
  * *Visibility:* Scoped to what the user is allowed to see (their own, their team's, or all).
* `POST /assets`: Create an asset. Include `"custom_fields": { "field_key": "value" }` inside the payload based on active custom fields.
* `GET /assets/{id}`: Get asset details.
* `PATCH /assets/{id}`: Update asset (e.g., status changes, re-assignment to new custodian).
* `POST /assets/import`: Upload a CSV/XLSX file to bulk create assets.
  * *FormData:* `file` (File), `mappings` (JSON string array: `[{"source_column": "CSV Header", "target_field": "db_field_or_custom_key"}]`).
* `GET /assets/export/excel`: Downloads an Excel file of the asset grid.

### 2.5 Sales Tracking (`/sales`)

Tracks sales deals and pipelines.
* **Schema Highlights:** `client_name`, `product_service`, `amount`, `status` (`lead`, `negotiation`, `won`, `lost`), `closing_date`, `user_id` (sales rep).
* `GET /sales`: List sales records. Scoped automatically by hierarchy.
* `GET /sales/aggregate`: Returns metrics grouped by status.
  * *Response Example:* `[{"status": "won", "total_amount": 50000, "count": 10}, ...]`
  * **Frontend Use:** Ideal for rendering dashboard pipeline charts (Funnel/Bar charts).
* `POST /sales`: Create a sales record.
* `GET /sales/{id}`: Get sales details.
* `PATCH /sales/{id}`: Update sales deal (e.g., moving from `lead` -> `won`).
* `POST /sales/import`: Bulk import sales.
* `GET /sales/export/excel`: Export sales to Excel.

### 2.6 KRA & Appraisals (`/kra`)

Manages Key Result Areas and the performance review cycles.
* **Schema Highlights:** `title`, `description`, `weightage`, `cycle` (e.g., "Q1-2026"), `status`, `employee_self_rating`, `manager_rating`.
* **Statuses:** `draft` -> `pending_approval` -> `approved` -> `in_progress` -> `review_submitted` -> `completed` (or `rejected`).
* `GET /kra`: List KRAs.
  * *Query Params:* `cycle` (e.g., filter by Q1), `user_id` (Manager viewing a specific team member).
* `POST /kra`: Assign a KRA to a user.
* `GET /kra/{id}`: Get KRA details.
* `PATCH /kra/{id}`: Update KRA. State transitions depend on role:
  * **Employee:** Can submit `employee_self_rating`, `employee_comment`, and change status to `review_submitted`.
  * **Manager/Admin:** Can submit `manager_rating`, `manager_comment`, `rejection_reason` and change status to `approved`, `rejected`, or `completed`.

---

## 3. Implementation Workflows for Frontend

### Workflow 1: Dynamic Forms (Assets & Sales)
1. User navigates to "Create Asset".
2. **Fetch:** `GET /custom-fields/asset_management`.
3. **Render:** Standard fields (Name, Category, Status) + dynamically map over the fetched custom fields to render inputs based on `field_type` (e.g., if `dropdown`, render a `<select>` using `dropdown_options`).
4. **Submit:** Wrap standard values at the root of the JSON payload, and nest custom field responses inside the `"custom_fields": {}` dict using `field_key`.

### Workflow 2: File Imports
1. User selects a CSV/XLSX file.
2. Frontend parses the file headers locally.
3. Frontend renders a mapping UI: *Match CSV Columns to Database Fields (Standard + Custom)*.
4. User completes mapping.
5. Frontend sends a `multipart/form-data` request to `/import` with the file and the stringified mapping array.
6. Display the returned `ImportResult` to the user showing successful rows and errors.

### Workflow 3: KRA Review Cycle
1. **Goal Setting:** Manager goes to team member's profile, creates KRAs (`POST /kra`) for `cycle="2026-H1"`.
2. **Approval:** Employee reviews them. Once agreed, manager sets status to `approved`.
3. **Mid-Cycle:** Status is set to `in_progress`.
4. **Self-Review Phase:** Employee opens KRA, inputs `employee_self_rating` and `employee_comment`, sets status to `review_submitted`.
5. **Manager Review:** Manager views the submitted KRA, inputs `manager_rating` and `manager_comment`, and sets status to `completed`.

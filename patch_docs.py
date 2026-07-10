import re

with open('kubera_full_api_reference.md', 'r') as f:
    content = f.read()

replacements = {
    "### GET /api/v1/users\n": "### GET /api/v1/users\n**Role Restriction**: Admin only\n",
    "### POST /api/v1/users\n": "### POST /api/v1/users\n**Role Restriction**: Admin only\n",
    "### GET /api/v1/users/me/reports\n": "### GET /api/v1/users/me/reports\n**Role Restriction**: Manager or Admin only\n",
    "### PATCH /api/v1/users/{user_id}/deactivate\n": "### PATCH /api/v1/users/{user_id}/deactivate\n**Role Restriction**: Admin only\n",
    "### POST /api/v1/custom-fields/{module_name}\n": "### POST /api/v1/custom-fields/{module_name}\n**Role Restriction**: Admin only\n",
    "### PATCH /api/v1/custom-fields/{module_name}/{field_id}\n": "### PATCH /api/v1/custom-fields/{module_name}/{field_id}\n**Role Restriction**: Admin only\n",
    "### PATCH /api/v1/custom-fields/{module_name}/{field_id}/deactivate\n": "### PATCH /api/v1/custom-fields/{module_name}/{field_id}/deactivate\n**Role Restriction**: Admin only\n",
    "### PATCH /api/v1/custom-fields/{module_name}/{field_id}/reactivate\n": "### PATCH /api/v1/custom-fields/{module_name}/{field_id}/reactivate\n**Role Restriction**: Admin only\n",
}

for old, new in replacements.items():
    content = content.replace(old, new)

content = content.replace(
    "All endpoints are authenticated via JWT Bearer tokens unless otherwise specified.",
    "**Auth Requirement**: All endpoints are authenticated via JWT Bearer tokens. A `Authorization: Bearer <token>` header is required."
)

content = content.replace(
    "## Module: assets\n", 
    "## Module: assets\n\n**Role Restrictions**: Endpoints are automatically scoped by hierarchy. Admins see all. Managers see their own and their direct reports' assets. Employees see only their assigned assets.\n"
)
content = content.replace(
    "## Module: sales\n", 
    "## Module: sales\n\n**Role Restrictions**: Endpoints are automatically scoped by hierarchy. Admins see all. Managers see their own and their direct reports' sales. Employees see only their assigned sales records.\n"
)
content = content.replace(
    "## Module: kra\n", 
    "## Module: kra\n\n**Role Restrictions**: Endpoints are automatically scoped by hierarchy. Endpoints enforce strict status transitions (e.g., only managers can approve/reject, only owners can submit self-reviews).\n"
)

with open('kubera_full_api_reference.md', 'w') as f:
    f.write(content)

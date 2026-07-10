# Kubera V1 - Complete API Reference

This document provides the full, current API reference for the Kubera backend.
**Auth Requirement**: All endpoints are authenticated via JWT Bearer tokens. A `Authorization: Bearer <token>` header is required.

## Impact of Role-Based Access Control on Legacy Modules
With the introduction of the `admin`, `manager`, and `employee` roles, older modules (such as **DocVault**, **AuditEase**, **Compliance**, **Activity**) which historically relied on `get_current_company_user` now implicitly allow **any authenticated company user (including employees and managers)** to access and modify data within the company's tenant scope. DocVault's `TenantScopedMixin` still correctly scopes data to the `company_id`, but role-based restrictions are absent on these older endpoints. **Auditor auth and engagements** remain completely unaffected, as they use a completely separate auth token type and table.

## Module: auth

### POST /api/v1/auth/companies
**Summary**: Create Company

**Request Body**:
- Content-Type: `application/json` (Schema: `CompanyCreateRequest`)

**Responses**:
- `201`: Successful Response -> `CompanyWithAdmin`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/auth/company/login
**Summary**: Company Login

**Request Body**:
- Content-Type: `application/json` (Schema: `LoginRequest`)

**Responses**:
- `200`: Successful Response -> `TokenResponse`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/auth/company/refresh
**Summary**: Company Refresh

**Request Body**:
- Content-Type: `application/json` (Schema: `RefreshRequest`)

**Responses**:
- `200`: Successful Response -> `TokenResponse`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/auth/company/me
**Summary**: Company Me

**Responses**:
- `200`: Successful Response -> `CompanyUserOut`

### POST /api/v1/auth/auditor/register
**Summary**: Auditor Register

**Request Body**:
- Content-Type: `application/json` (Schema: `AuditorRegister`)

**Responses**:
- `201`: Successful Response -> `AuditorOut`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/auth/auditor/login
**Summary**: Auditor Login

**Request Body**:
- Content-Type: `application/json` (Schema: `LoginRequest`)

**Responses**:
- `200`: Successful Response -> `TokenResponse`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/auth/auditor/refresh
**Summary**: Auditor Refresh

**Request Body**:
- Content-Type: `application/json` (Schema: `RefreshRequest`)

**Responses**:
- `200`: Successful Response -> `TokenResponse`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/auth/auditor/me
**Summary**: Auditor Me

**Responses**:
- `200`: Successful Response -> `AuditorOut`

## Module: users

### GET /api/v1/users
**Role Restriction**: Admin only
**Summary**: List Users

**Responses**:
- `200`: Successful Response -> `Array[UserResponse]`

### POST /api/v1/users
**Role Restriction**: Admin only
**Summary**: Create User

**Request Body**:
- Content-Type: `application/json` (Schema: `UserCreate`)

**Responses**:
- `201`: Successful Response -> `UserResponse`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/users/me
**Summary**: Get Me

**Responses**:
- `200`: Successful Response -> `UserResponse`

### GET /api/v1/users/me/reports
**Role Restriction**: Manager or Admin only
**Summary**: Get My Reports

**Responses**:
- `200`: Successful Response -> `Array[UserResponse]`

### GET /api/v1/users/{user_id}
**Summary**: Get User

**Responses**:
- `200`: Successful Response -> `UserResponse`
- `422`: Validation Error -> `HTTPValidationError`

### PATCH /api/v1/users/{user_id}
**Summary**: Update User

**Request Body**:
- Content-Type: `application/json` (Schema: `UserUpdate`)

**Responses**:
- `200`: Successful Response -> `UserResponse`
- `422`: Validation Error -> `HTTPValidationError`

### PATCH /api/v1/users/{user_id}/deactivate
**Role Restriction**: Admin only
**Summary**: Deactivate User

**Responses**:
- `200`: Successful Response -> `UserResponse`
- `422`: Validation Error -> `HTTPValidationError`

## Module: custom-fields

### GET /api/v1/custom-fields/{module}
**Summary**: List Custom Fields

**Responses**:
- `200`: Successful Response -> `Array[CustomFieldResponse]`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/custom-fields/{module}
**Summary**: Create Custom Field

**Request Body**:
- Content-Type: `application/json` (Schema: `CustomFieldCreate`)

**Responses**:
- `201`: Successful Response -> `CustomFieldResponse`
- `422`: Validation Error -> `HTTPValidationError`

### PATCH /api/v1/custom-fields/{module}/{field_id}
**Summary**: Update Custom Field

**Request Body**:
- Content-Type: `application/json` (Schema: `CustomFieldUpdate`)

**Responses**:
- `200`: Successful Response -> `CustomFieldResponse`
- `422`: Validation Error -> `HTTPValidationError`

### PATCH /api/v1/custom-fields/{module}/{field_id}/deactivate
**Summary**: Deactivate Custom Field

**Responses**:
- `200`: Successful Response -> `CustomFieldResponse`
- `422`: Validation Error -> `HTTPValidationError`

### PATCH /api/v1/custom-fields/{module}/{field_id}/reactivate
**Summary**: Reactivate Custom Field

**Responses**:
- `200`: Successful Response -> `CustomFieldResponse`
- `422`: Validation Error -> `HTTPValidationError`

## Module: assets

**Role Restrictions**: Endpoints are automatically scoped by hierarchy. Admins see all. Managers see their own and their direct reports' assets. Employees see only their assigned assets.

### GET /api/v1/assets
**Summary**: List Assets

**Responses**:
- `200`: Successful Response -> `Array[AssetResponse]`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/assets
**Summary**: Create Asset

**Request Body**:
- Content-Type: `application/json` (Schema: `AssetCreate`)

**Responses**:
- `201`: Successful Response -> `AssetResponse`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/assets/{asset_id}
**Summary**: Get Asset

**Responses**:
- `200`: Successful Response -> `AssetResponse`
- `422`: Validation Error -> `HTTPValidationError`

### PATCH /api/v1/assets/{asset_id}
**Summary**: Update Asset

**Request Body**:
- Content-Type: `application/json` (Schema: `AssetUpdate`)

**Responses**:
- `200`: Successful Response -> `AssetResponse`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/assets/import
**Summary**: Import Assets

**Request Body**:
- Content-Type: `multipart/form-data` (Schema: `Body_import_assets_api_v1_assets_import_post`)

**Responses**:
- `200`: Successful Response -> `ImportResult`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/assets/export/excel
**Summary**: Export Assets

**Responses**:
- `200`: Successful Response

## Module: sales

**Role Restrictions**: Endpoints are automatically scoped by hierarchy. Admins see all. Managers see their own and their direct reports' sales. Employees see only their assigned sales records.

### GET /api/v1/sales
**Summary**: List Sales

**Responses**:
- `200`: Successful Response -> `Array[SalesRecordResponse]`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/sales
**Summary**: Create Sales Record

**Request Body**:
- Content-Type: `application/json` (Schema: `SalesRecordCreate`)

**Responses**:
- `201`: Successful Response -> `SalesRecordResponse`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/sales/aggregate
**Summary**: Aggregate Sales

**Responses**:
- `200`: Successful Response

### GET /api/v1/sales/{sales_id}
**Summary**: Get Sales Record

**Responses**:
- `200`: Successful Response -> `SalesRecordResponse`
- `422`: Validation Error -> `HTTPValidationError`

### PATCH /api/v1/sales/{sales_id}
**Summary**: Update Sales Record

**Request Body**:
- Content-Type: `application/json` (Schema: `SalesRecordUpdate`)

**Responses**:
- `200`: Successful Response -> `SalesRecordResponse`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/sales/import
**Summary**: Import Sales

**Request Body**:
- Content-Type: `multipart/form-data` (Schema: `Body_import_sales_api_v1_sales_import_post`)

**Responses**:
- `200`: Successful Response -> `ImportResult`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/sales/export/excel
**Summary**: Export Sales

**Responses**:
- `200`: Successful Response

## Module: kra

**Role Restrictions**: Endpoints are automatically scoped by hierarchy. Endpoints enforce strict status transitions (e.g., only managers can approve/reject, only owners can submit self-reviews).

### GET /api/v1/kra
**Summary**: List Kras

**Responses**:
- `200`: Successful Response -> `Array[KRAResponse]`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/kra
**Summary**: Create Kra

**Request Body**:
- Content-Type: `application/json` (Schema: `KRACreate`)

**Responses**:
- `201`: Successful Response -> `KRAResponse`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/kra/{kra_id}
**Summary**: Get Kra

**Responses**:
- `200`: Successful Response -> `KRAResponse`
- `422`: Validation Error -> `HTTPValidationError`

### PATCH /api/v1/kra/{kra_id}
**Summary**: Update Kra

**Request Body**:
- Content-Type: `application/json` (Schema: `KRAUpdate`)

**Responses**:
- `200`: Successful Response -> `KRAResponse`
- `422`: Validation Error -> `HTTPValidationError`

## Module: activity-log

### GET /api/v1/activity-log
**Summary**: List Activity Logs

**Responses**:
- `200`: Successful Response -> `Array[ActivityLogOut]`
- `422`: Validation Error -> `HTTPValidationError`

## Module: notifications

### GET /api/v1/notifications
**Summary**: List Notifications Company

**Responses**:
- `200`: Successful Response -> `Array[NotificationOut]`

### PATCH /api/v1/notifications/{notification_id}/read
**Summary**: Mark Notification Read Company

**Responses**:
- `200`: Successful Response -> `NotificationOut`
- `422`: Validation Error -> `HTTPValidationError`

## Module: docvault

### GET /api/v1/docvault/buckets
**Summary**: List Buckets

**Responses**:
- `200`: Successful Response -> `Array[BucketResponse]`

### POST /api/v1/docvault/buckets
**Summary**: Create Bucket

**Request Body**:
- Content-Type: `application/json` (Schema: `BucketCreate`)

**Responses**:
- `201`: Successful Response -> `BucketResponse`
- `422`: Validation Error -> `HTTPValidationError`

### DELETE /api/v1/docvault/buckets/{bucket_id}
**Summary**: Delete Bucket

**Responses**:
- `204`: Successful Response
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/docvault/documents
**Summary**: Upload Document

**Request Body**:
- Content-Type: `multipart/form-data` (Schema: `Body_upload_document_api_v1_docvault_documents_post`)

**Responses**:
- `201`: Successful Response -> `DocumentResponse`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/docvault/documents
**Summary**: List Documents

**Responses**:
- `200`: Successful Response -> `Array[DocumentResponse]`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/docvault/documents/{document_id}/versions
**Summary**: Upload Document Version

**Request Body**:
- Content-Type: `multipart/form-data` (Schema: `Body_upload_document_version_api_v1_docvault_documents__document_id__versions_post`)

**Responses**:
- `200`: Successful Response -> `DocumentResponse`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/docvault/documents/search
**Summary**: Search Documents

**Responses**:
- `200`: Successful Response -> `Array[DocumentResponse]`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/docvault/documents/{document_id}
**Summary**: Get Document

**Responses**:
- `200`: Successful Response -> `DocumentResponse`
- `422`: Validation Error -> `HTTPValidationError`

### PATCH /api/v1/docvault/documents/{document_id}
**Summary**: Update Document

**Request Body**:
- Content-Type: `application/json` (Schema: `DocumentUpdate`)

**Responses**:
- `200`: Successful Response -> `DocumentResponse`
- `422`: Validation Error -> `HTTPValidationError`

### DELETE /api/v1/docvault/documents/{document_id}
**Summary**: Delete Document

**Responses**:
- `204`: Successful Response
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/docvault/documents/{document_id}/download
**Summary**: Download Document

**Responses**:
- `200`: Successful Response
- `422`: Validation Error -> `HTTPValidationError`

## Module: auditease-company

### POST /api/v1/auditease/trial-balance/import
**Summary**: Import Trial Balance

**Request Body**:
- Content-Type: `application/json`

**Responses**:
- `200`: Successful Response -> `Array[TrialBalanceAccountResponse]`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/auditease/trial-balance
**Summary**: Get Trial Balance

**Responses**:
- `200`: Successful Response -> `Array[TrialBalanceAccountResponse]`

### POST /api/v1/auditease/ledgers/{ledger_id}/map-group
**Summary**: Map Ledger Group

**Responses**:
- `200`: Successful Response -> `TrialBalanceAccountResponse`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/auditease/engagements
**Summary**: List Engagements

**Responses**:
- `200`: Successful Response -> `Array[AuditEngagementResponse]`

### POST /api/v1/auditease/engagements
**Summary**: Create Engagement

**Request Body**:
- Content-Type: `application/json` (Schema: `AuditEngagementCreate`)

**Responses**:
- `201`: Successful Response -> `AuditEngagementResponse`
- `422`: Validation Error -> `HTTPValidationError`

### PATCH /api/v1/auditease/engagements/{engagement_id}/close
**Summary**: Close Engagement

**Responses**:
- `200`: Successful Response -> `AuditEngagementResponse`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/auditease/engagements/{engagement_id}/invite-auditor
**Summary**: Invite Auditor

**Request Body**:
- Content-Type: `application/json` (Schema: `AuditorInvite`)

**Responses**:
- `200`: Successful Response
- `422`: Validation Error -> `HTTPValidationError`

### PATCH /api/v1/auditease/entries/{entry_id}/approve
**Summary**: Approve Reject Entry

**Request Body**:
- Content-Type: `application/json` (Schema: `EntryApproval`)

**Responses**:
- `200`: Successful Response -> `AuditEntryResponse`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/auditease/engagements/{engagement_id}/requirement-requests
**Summary**: List Requirements

**Responses**:
- `200`: Successful Response -> `Array[RequirementRequestResponse]`
- `422`: Validation Error -> `HTTPValidationError`

### PATCH /api/v1/auditease/engagements/{engagement_id}/requirement-requests/{req_id}/fulfill
**Summary**: Fulfill Requirement

**Request Body**:
- Content-Type: `application/json` (Schema: `RequirementFulfill`)

**Responses**:
- `200`: Successful Response -> `RequirementRequestResponse`
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/auditease/engagements/{engagement_id}/queries
**Summary**: List Queries

**Responses**:
- `200`: Successful Response -> `Array[QueryResponse]`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/auditease/engagements/{engagement_id}/queries/{query_id}/messages
**Summary**: Add Query Message

**Request Body**:
- Content-Type: `application/json` (Schema: `QueryMessageCreate`)

**Responses**:
- `200`: Successful Response -> `QueryMessageResponse`
- `422`: Validation Error -> `HTTPValidationError`

## Module: auditease-auditor

### GET /api/v1/auditor/engagements
**Summary**: List Engagements

**Responses**:
- `200`: Successful Response -> `Array[AuditEngagementResponse]`

### POST /api/v1/auditor/engagements/{engagement_id}/accept
**Summary**: Accept Engagement

**Responses**:
- `200`: Successful Response
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/auditor/engagements/{engagement_id}/trial-balance
**Summary**: Get Trial Balance

**Responses**:
- `200`: Successful Response -> `Array[TrialBalanceAccountResponse]`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/auditor/engagements/{engagement_id}/entries
**Summary**: Create Entry

**Request Body**:
- Content-Type: `application/json` (Schema: `AuditEntryCreate`)

**Responses**:
- `201`: Successful Response -> `AuditEntryResponse`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/auditor/engagements/{engagement_id}/requirement-requests
**Summary**: Create Requirement

**Request Body**:
- Content-Type: `application/json` (Schema: `RequirementRequestCreate`)

**Responses**:
- `200`: Successful Response -> `RequirementRequestResponse`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/auditor/engagements/{engagement_id}/queries
**Summary**: Create Query

**Request Body**:
- Content-Type: `application/json` (Schema: `QueryCreate`)

**Responses**:
- `200`: Successful Response -> `QueryResponse`
- `422`: Validation Error -> `HTTPValidationError`

### POST /api/v1/auditor/engagements/{engagement_id}/queries/{query_id}/messages
**Summary**: Add Query Message

**Request Body**:
- Content-Type: `application/json` (Schema: `QueryMessageCreate`)

**Responses**:
- `200`: Successful Response -> `QueryMessageResponse`
- `422`: Validation Error -> `HTTPValidationError`

## Module: secretarialease

### GET /api/v1/secretarial/document-types
**Summary**: List Document Types

**Responses**:
- `200`: Successful Response -> `Array[DocumentTypeResponse]`

### POST /api/v1/secretarial/document-types
**Summary**: Create Document Type

**Request Body**:
- Content-Type: `application/json` (Schema: `DocumentTypeCreate`)

**Responses**:
- `201`: Successful Response -> `DocumentTypeResponse`
- `422`: Validation Error -> `HTTPValidationError`

### PUT /api/v1/secretarial/document-types/{dt_id}
**Summary**: Update Document Type

**Request Body**:
- Content-Type: `application/json` (Schema: `DocumentTypeCreate`)

**Responses**:
- `200`: Successful Response -> `DocumentTypeResponse`
- `422`: Validation Error -> `HTTPValidationError`

### DELETE /api/v1/secretarial/document-types/{dt_id}
**Summary**: Delete Document Type

**Responses**:
- `200`: Successful Response
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/secretarial/meeting-records
**Summary**: List Meeting Records

**Responses**:
- `200`: Successful Response -> `Array[MeetingRecordResponse]`

### POST /api/v1/secretarial/meeting-records
**Summary**: Create Meeting Record

**Request Body**:
- Content-Type: `application/json` (Schema: `MeetingRecordCreate`)

**Responses**:
- `201`: Successful Response -> `MeetingRecordResponse`
- `422`: Validation Error -> `HTTPValidationError`

## Module: roc-compliance

### GET /api/v1/roc/document-types
**Summary**: List Document Types

**Responses**:
- `200`: Successful Response -> `Array[DocumentTypeResponse]`

### POST /api/v1/roc/document-types
**Summary**: Create Document Type

**Request Body**:
- Content-Type: `application/json` (Schema: `DocumentTypeCreate`)

**Responses**:
- `201`: Successful Response -> `DocumentTypeResponse`
- `422`: Validation Error -> `HTTPValidationError`

### PUT /api/v1/roc/document-types/{dt_id}
**Summary**: Update Document Type

**Request Body**:
- Content-Type: `application/json` (Schema: `DocumentTypeCreate`)

**Responses**:
- `200`: Successful Response -> `DocumentTypeResponse`
- `422`: Validation Error -> `HTTPValidationError`

### DELETE /api/v1/roc/document-types/{dt_id}
**Summary**: Delete Document Type

**Responses**:
- `200`: Successful Response
- `422`: Validation Error -> `HTTPValidationError`

### GET /api/v1/roc/meeting-records
**Summary**: List Meeting Records

**Responses**:
- `200`: Successful Response -> `Array[MeetingRecordResponse]`

### POST /api/v1/roc/meeting-records
**Summary**: Create Meeting Record

**Request Body**:
- Content-Type: `application/json` (Schema: `MeetingRecordCreate`)

**Responses**:
- `201`: Successful Response -> `MeetingRecordResponse`
- `422`: Validation Error -> `HTTPValidationError`

## Schemas

### ActivityLogOut
- `id` (string)
- `company_id` (string)
- `actor_type` (string)
- `actor_id` (string)
- `action` (string)
- `entity_type` (string)
- `entity_id` (string)
- `metadata_` ([{}, {'type': 'null'}])
- `created_at` (string)

### AssetCategory

### AssetCreate
- `asset_name` (string)
- `serial_number` ([{'type': 'string'}, {'type': 'null'}])
- `category` (unknown)
- `status` (unknown)
- `purchase_date` ([{'type': 'string', 'format': 'date'}, {'type': 'null'}])
- `purchase_cost` ([{'type': 'number'}, {'type': 'null'}])
- `depreciation_rate` ([{'type': 'number'}, {'type': 'null'}])
- `custodian_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `document_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `custom_fields` (object)

### AssetResponse
- `id` (string)
- `company_id` (string)
- `asset_name` (string)
- `serial_number` ([{'type': 'string'}, {'type': 'null'}])
- `category` (unknown)
- `status` (unknown)
- `purchase_date` ([{'type': 'string', 'format': 'date'}, {'type': 'null'}])
- `purchase_cost` ([{'type': 'number'}, {'type': 'null'}])
- `depreciation_rate` ([{'type': 'number'}, {'type': 'null'}])
- `custodian_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `document_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `custom_fields` (object)
- `created_at` (string)
- `updated_at` (string)

### AssetStatus

### AssetUpdate
- `asset_name` ([{'type': 'string'}, {'type': 'null'}])
- `serial_number` ([{'type': 'string'}, {'type': 'null'}])
- `category` ([{'$ref': '#/components/schemas/AssetCategory'}, {'type': 'null'}])
- `status` ([{'$ref': '#/components/schemas/AssetStatus'}, {'type': 'null'}])
- `purchase_date` ([{'type': 'string', 'format': 'date'}, {'type': 'null'}])
- `purchase_cost` ([{'type': 'number'}, {'type': 'null'}])
- `depreciation_rate` ([{'type': 'number'}, {'type': 'null'}])
- `custodian_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `document_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `custom_fields` ([{'additionalProperties': True, 'type': 'object'}, {'type': 'null'}])

### AuditEngagementCreate
- `period_label` (string)

### AuditEngagementResponse
- `period_label` (string)
- `id` (string)
- `company_id` (string)
- `status` (unknown)
- `created_by` (string)
- `created_at` (string)
- `updated_at` (string)

### AuditEntryCreate
- `code` ([{'type': 'string'}, {'type': 'null'}])
- `description` (string)
- `lines` (array)

### AuditEntryLineBase
- `ledger_id` (string)
- `side` (unknown)
- `amount` (number)

### AuditEntryLineResponse
- `ledger_id` (string)
- `side` (unknown)
- `amount` (number)
- `id` (string)
- `entry_id` (string)

### AuditEntryResponse
- `id` (string)
- `engagement_id` (string)
- `created_by` (string)
- `code` ([{'type': 'string'}, {'type': 'null'}])
- `description` (string)
- `status` (unknown)
- `created_at` (string)
- `updated_at` (string)
- `lines` (array)

### AuditEntryStatus

### AuditorInvite
- `email` (string)

### AuditorOut
- `id` (string)
- `email` (string)
- `name` (string)

### AuditorRegister
- `email` (string)
- `password` (string)
- `name` (string)

### Body_import_assets_api_v1_assets_import_post
- `file` (string)
- `mappings` (string)

### Body_import_sales_api_v1_sales_import_post
- `file` (string)
- `mappings` (string)

### Body_upload_document_api_v1_docvault_documents_post
- `title` (string)
- `file` (string)
- `bucket_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `tags` ([{'type': 'string'}, {'type': 'null'}])
- `is_editable` (boolean)

### Body_upload_document_version_api_v1_docvault_documents__document_id__versions_post
- `file` (string)

### BucketCreate
- `name` (string)

### BucketResponse
- `id` (string)
- `name` (string)
- `company_id` (string)
- `created_by` (string)
- `created_at` (string)
- `updated_at` (string)

### CompanyCreateRequest
- `name` (string)
- `admin` (unknown)

### CompanyOut
- `id` (string)
- `name` (string)

### CompanyUserCreate
- `email` (string)
- `password` (string)

### CompanyUserOut
- `id` (string)
- `company_id` (string)
- `email` (string)
- `role` (string)
- `manager_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `full_name` (string)
- `designation` ([{'type': 'string'}, {'type': 'null'}])
- `department` ([{'type': 'string'}, {'type': 'null'}])
- `is_active` (boolean)

### CompanyWithAdmin
- `company` (unknown)
- `admin` (unknown)

### ComplianceDomain

### CustomFieldCreate
- `field_name` (string)
- `field_key` (string)
- `field_type` (unknown)
- `is_required` (boolean)
- `dropdown_options` ([{'items': {'type': 'string'}, 'type': 'array'}, {'type': 'null'}])
- `display_order` (integer)

### CustomFieldModule

### CustomFieldResponse
- `id` (string)
- `module` (unknown)
- `field_name` (string)
- `field_key` (string)
- `field_type` (unknown)
- `is_required` (boolean)
- `dropdown_options` ([{'items': {'type': 'string'}, 'type': 'array'}, {'type': 'null'}])
- `display_order` (integer)
- `is_active` (boolean)
- `company_id` (string)
- `created_at` (string)
- `updated_at` (string)

### CustomFieldType

### CustomFieldUpdate
- `field_name` ([{'type': 'string'}, {'type': 'null'}])
- `is_required` ([{'type': 'boolean'}, {'type': 'null'}])
- `dropdown_options` ([{'items': {'type': 'string'}, 'type': 'array'}, {'type': 'null'}])
- `display_order` ([{'type': 'integer'}, {'type': 'null'}])

### DocumentResponse
- `id` (string)
- `company_id` (string)
- `current_version_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `bucket_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `status` (unknown)
- `title` (string)
- `doc_type_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `tags` (array)
- `is_editable` (boolean)
- `created_by` (string)
- `created_at` (string)
- `updated_at` (string)
- `versions` (array)

### DocumentStatus

### DocumentTypeCreate
- `name` (string)
- `template_file_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `metadata_schema` ([{'additionalProperties': True, 'type': 'object'}, {'type': 'null'}])
- `due_date_rule` ([{'type': 'string'}, {'type': 'null'}])

### DocumentTypeResponse
- `name` (string)
- `template_file_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `metadata_schema` ([{'additionalProperties': True, 'type': 'object'}, {'type': 'null'}])
- `due_date_rule` ([{'type': 'string'}, {'type': 'null'}])
- `id` (string)
- `company_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `domain` (unknown)
- `created_at` (string)
- `updated_at` (string)

### DocumentUpdate
- `status` ([{'$ref': '#/components/schemas/DocumentStatus'}, {'type': 'null'}])
- `bucket_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `tags` ([{'items': {'type': 'string'}, 'type': 'array'}, {'type': 'null'}])
- `is_editable` ([{'type': 'boolean'}, {'type': 'null'}])

### DocumentVersionResponse
- `id` (string)
- `document_id` (string)
- `original_filename` (string)
- `mime_type` (string)
- `size_bytes` (integer)
- `checksum` (string)
- `uploaded_by` (string)
- `uploaded_at` (string)
- `version_number` (integer)

### EngagementStatus

### EntryApproval
- `status` (unknown)

### EntryLineSide

### HTTPValidationError
- `detail` (array)

### ImportResult
- `imported` (integer)
- `skipped` (integer)
- `errors` (array)

### KRACreate
- `title` (string)
- `description` (string)
- `weightage` (number)
- `target_metric` ([{'type': 'string'}, {'type': 'null'}])
- `cycle` (string)
- `user_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])

### KRAResponse
- `id` (string)
- `company_id` (string)
- `title` (string)
- `description` (string)
- `weightage` (number)
- `target_metric` ([{'type': 'string'}, {'type': 'null'}])
- `cycle` (string)
- `status` (unknown)
- `user_id` (string)
- `manager_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `employee_self_rating` ([{'type': 'number'}, {'type': 'null'}])
- `employee_comment` ([{'type': 'string'}, {'type': 'null'}])
- `manager_rating` ([{'type': 'number'}, {'type': 'null'}])
- `manager_comment` ([{'type': 'string'}, {'type': 'null'}])
- `rejection_reason` ([{'type': 'string'}, {'type': 'null'}])
- `created_at` (string)
- `updated_at` (string)

### KRAStatus

### KRAUpdate
- `title` ([{'type': 'string'}, {'type': 'null'}])
- `description` ([{'type': 'string'}, {'type': 'null'}])
- `weightage` ([{'type': 'number'}, {'type': 'null'}])
- `target_metric` ([{'type': 'string'}, {'type': 'null'}])
- `status` ([{'$ref': '#/components/schemas/KRAStatus'}, {'type': 'null'}])
- `employee_self_rating` ([{'type': 'number'}, {'type': 'null'}])
- `employee_comment` ([{'type': 'string'}, {'type': 'null'}])
- `manager_rating` ([{'type': 'number'}, {'type': 'null'}])
- `manager_comment` ([{'type': 'string'}, {'type': 'null'}])
- `rejection_reason` ([{'type': 'string'}, {'type': 'null'}])

### LoginRequest
- `email` (string)
- `password` (string)

### MeetingRecordCreate
- `doc_type_id` (string)
- `document_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `structured_metadata` ([{'additionalProperties': True, 'type': 'object'}, {'type': 'null'}])

### MeetingRecordResponse
- `doc_type_id` (string)
- `document_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `structured_metadata` ([{'additionalProperties': True, 'type': 'object'}, {'type': 'null'}])
- `id` (string)
- `company_id` (string)
- `created_at` (string)
- `updated_at` (string)

### NotificationOut
- `id` (string)
- `recipient_type` (string)
- `recipient_id` (string)
- `type` (string)
- `payload` ([{}, {'type': 'null'}])
- `read_at` ([{'type': 'string', 'format': 'date-time'}, {'type': 'null'}])
- `created_at` (string)

### QueryCreate
- `initial_message` (string)
- `attached_document_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])

### QueryMessageCreate
- `text` (string)
- `attached_document_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])

### QueryMessageResponse
- `id` (string)
- `query_id` (string)
- `sender_type` (unknown)
- `sender_id` (string)
- `text` (string)
- `attached_document_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `created_at` (string)

### QueryResponse
- `id` (string)
- `engagement_id` (string)
- `opened_by` (string)
- `status` (unknown)
- `created_at` (string)
- `updated_at` (string)
- `messages` (array)

### QueryStatus

### RefreshRequest
- `refresh_token` (string)

### RequestStatus

### RequirementFulfill
- `document_id` (string)

### RequirementRequestCreate
- `description` (string)

### RequirementRequestResponse
- `id` (string)
- `engagement_id` (string)
- `raised_by` (string)
- `description` (string)
- `status` (unknown)
- `fulfilled_document_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `created_at` (string)
- `updated_at` (string)

### SalesRecordCreate
- `client_name` (string)
- `product_service` (string)
- `amount` (number)
- `status` (unknown)
- `closing_date` ([{'type': 'string', 'format': 'date'}, {'type': 'null'}])
- `user_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `custom_fields` (object)

### SalesRecordResponse
- `id` (string)
- `company_id` (string)
- `client_name` (string)
- `product_service` (string)
- `amount` (number)
- `status` (unknown)
- `closing_date` ([{'type': 'string', 'format': 'date'}, {'type': 'null'}])
- `user_id` (string)
- `custom_fields` (object)
- `created_at` (string)
- `updated_at` (string)

### SalesRecordUpdate
- `client_name` ([{'type': 'string'}, {'type': 'null'}])
- `product_service` ([{'type': 'string'}, {'type': 'null'}])
- `amount` ([{'type': 'number'}, {'type': 'null'}])
- `status` ([{'$ref': '#/components/schemas/SalesStatus'}, {'type': 'null'}])
- `closing_date` ([{'type': 'string', 'format': 'date'}, {'type': 'null'}])
- `user_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `custom_fields` ([{'additionalProperties': True, 'type': 'object'}, {'type': 'null'}])

### SalesStatus

### SenderType

### TBImportRow
- `ledger_code` ([{'type': 'string'}, {'type': 'null'}])
- `ledger_name` (string)
- `opening_balance` (number)
- `debit` (number)
- `credit` (number)
- `closing_balance` (number)

### TokenResponse
- `access_token` (string)
- `refresh_token` (string)
- `token_type` (string)
- `role` ([{'type': 'string'}, {'type': 'null'}])
- `full_name` ([{'type': 'string'}, {'type': 'null'}])

### TrialBalanceAccountResponse
- `ledger_code` ([{'type': 'string'}, {'type': 'null'}])
- `ledger_name` (string)
- `mapped_group_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `opening_balance` (number)
- `debit` (number)
- `credit` (number)
- `closing_balance` (number)
- `id` (string)
- `company_id` (string)
- `created_at` (string)
- `updated_at` (string)

### UserCreate
- `email` (string)
- `password` (string)
- `full_name` (string)
- `role` (unknown)
- `manager_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `designation` ([{'type': 'string'}, {'type': 'null'}])
- `department` ([{'type': 'string'}, {'type': 'null'}])

### UserResponse
- `id` (string)
- `email` (string)
- `full_name` (string)
- `role` (unknown)
- `manager_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `designation` ([{'type': 'string'}, {'type': 'null'}])
- `department` ([{'type': 'string'}, {'type': 'null'}])
- `is_active` (boolean)
- `company_id` (string)
- `created_at` (string)

### UserRole

### UserUpdate
- `full_name` ([{'type': 'string'}, {'type': 'null'}])
- `role` ([{'$ref': '#/components/schemas/UserRole'}, {'type': 'null'}])
- `manager_id` ([{'type': 'string', 'format': 'uuid'}, {'type': 'null'}])
- `designation` ([{'type': 'string'}, {'type': 'null'}])
- `department` ([{'type': 'string'}, {'type': 'null'}])
- `is_active` ([{'type': 'boolean'}, {'type': 'null'}])

### ValidationError
- `loc` (array)
- `msg` (string)
- `type` (string)


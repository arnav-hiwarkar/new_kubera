import json

with open('/tmp/openapi.json', 'r') as f:
    openapi = json.load(f)

md = "# Kubera V1 - Complete API Reference\n\n"
md += "This document provides the full, current API reference for the Kubera backend.\n"
md += "All endpoints are authenticated via JWT Bearer tokens unless otherwise specified.\n\n"

md += "## Impact of Role-Based Access Control on Legacy Modules\n"
md += "With the introduction of the `admin`, `manager`, and `employee` roles, older modules (such as **DocVault**, **AuditEase**, **Compliance**, **Activity**) which historically relied on `get_current_company_user` now implicitly allow **any authenticated company user (including employees and managers)** to access and modify data within the company's tenant scope. DocVault's `TenantScopedMixin` still correctly scopes data to the `company_id`, but role-based restrictions are absent on these older endpoints. **Auditor auth and engagements** remain completely unaffected, as they use a completely separate auth token type and table.\n\n"

paths = openapi.get('paths', {})

# Group by tags
tags = {}
for path, methods in paths.items():
    for method, details in methods.items():
        tag = details.get('tags', ['Other'])[0]
        if tag not in tags:
            tags[tag] = []
        tags[tag].append((path, method, details))

for tag, endpoints in tags.items():
    md += f"## Module: {tag}\n\n"
    for path, method, details in endpoints:
        md += f"### {method.upper()} {path}\n"
        md += f"**Summary**: {details.get('summary', 'No summary')}\n\n"
        
        # Request Body
        req_body = details.get('requestBody', {})
        if req_body:
            md += "**Request Body**:\n"
            content = req_body.get('content', {})
            for content_type, content_details in content.items():
                schema = content_details.get('schema', {})
                ref = schema.get('$ref', '')
                if ref:
                    ref_name = ref.split('/')[-1]
                    md += f"- Content-Type: `{content_type}` (Schema: `{ref_name}`)\n"
                else:
                    md += f"- Content-Type: `{content_type}`\n"
            md += "\n"
        
        # Responses
        md += "**Responses**:\n"
        responses = details.get('responses', {})
        for status, resp_details in responses.items():
            desc = resp_details.get('description', '')
            content = resp_details.get('content', {})
            schema_info = ""
            if content:
                for ct, c_details in content.items():
                    schema = c_details.get('schema', {})
                    ref = schema.get('$ref', '')
                    if ref:
                        schema_info = f" -> `{ref.split('/')[-1]}`"
                    elif schema.get('type') == 'array' and schema.get('items', {}).get('$ref'):
                        schema_info = f" -> `Array[{schema['items']['$ref'].split('/')[-1]}]`"
            md += f"- `{status}`: {desc}{schema_info}\n"
        md += "\n"

# Schemas
md += "## Schemas\n\n"
schemas = openapi.get('components', {}).get('schemas', {})
for schema_name, schema_details in schemas.items():
    md += f"### {schema_name}\n"
    props = schema_details.get('properties', {})
    if props:
        for prop_name, prop_details in props.items():
            p_type = prop_details.get('type', prop_details.get('anyOf', 'unknown'))
            md += f"- `{prop_name}` ({p_type})\n"
    md += "\n"

with open('kubera_full_api_reference.md', 'w') as f:
    f.write(md)


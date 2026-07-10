import uuid
from typing import List
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.custom_fields import CustomFieldDefinition, CustomFieldModule, CustomFieldType

async def validate_custom_fields(
    custom_fields: dict,
    company_id: uuid.UUID,
    module: CustomFieldModule,
    db: AsyncSession
) -> List[str]:
    """Validate a custom_fields JSONB dict against the company's field definitions.
    Returns a list of error messages (empty = valid)."""
    
    # Fetch active definitions
    result = await db.execute(
        select(CustomFieldDefinition)
        .where(
            CustomFieldDefinition.company_id == company_id,
            CustomFieldDefinition.module == module,
            CustomFieldDefinition.is_active == True
        )
    )
    definitions = result.scalars().all()
    def_map = {d.field_key: d for d in definitions}

    errors = []

    # Check required fields
    for d in definitions:
        if d.is_required and d.field_key not in custom_fields:
            errors.append(f"Field '{d.field_name}' is required.")

    # Validate types and constraints
    for key, val in custom_fields.items():
        if key not in def_map:
            # Ignore unknown keys (orphaned from deactivated fields)
            continue
        
        d = def_map[key]
        if val is None or val == "":
            if d.is_required:
                errors.append(f"Field '{d.field_name}' cannot be empty.")
            continue

        if d.field_type == CustomFieldType.number:
            try:
                float(val)
            except ValueError:
                errors.append(f"Field '{d.field_name}' must be a number.")
        elif d.field_type == CustomFieldType.date:
            try:
                datetime.fromisoformat(str(val))
            except ValueError:
                errors.append(f"Field '{d.field_name}' must be a valid ISO date.")
        elif d.field_type == CustomFieldType.dropdown:
            if d.dropdown_options and val not in d.dropdown_options:
                errors.append(f"Value for '{d.field_name}' is not in allowed options.")

    return errors

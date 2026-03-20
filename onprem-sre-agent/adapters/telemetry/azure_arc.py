from __future__ import annotations


class AzureArcClient:
    async def get_machine_context(self, machine_id: str) -> dict[str, str]:
        return {"machine_id": machine_id, "managed_by": "azure-arc"}

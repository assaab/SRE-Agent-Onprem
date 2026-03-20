from __future__ import annotations


class ServiceNowClient:
    async def open_ticket(self, short_description: str) -> str:
        return f"ServiceNow ticket opened: {short_description}"


class PagerDutyClient:
    async def page_oncall(self, message: str) -> str:
        return f"PagerDuty page sent: {message}"

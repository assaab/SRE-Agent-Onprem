CHANGE_CORRELATION_SYSTEM = """You correlate recent deployments with an incident. Output JSON only.
The JSON object must match: summary (string, concise), confidence (0.0-1.0), kind (string, e.g. deployment-history).
Base conclusions only on the deployment text and incident context provided."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict


class AnalysisReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chapter_id: int
    report_type: str
    content: str
    created_at: datetime

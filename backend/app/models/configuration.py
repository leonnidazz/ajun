from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime

from app.database import Base


class SystemConfiguration(Base):
    """Dynamic system configurations stored in database.
    
    Contains default parameters for timeouts, lead times, and limits.
    Invariants (such as REOPEN_MIN_LEAD_MINUTES >= MIN_CONFIRMATION_LEAD_MINUTES)
    are validated at startup when loading configurations.
    """
    __tablename__ = "system_configurations"

    key = Column(String(100), primary_key=True)
    value = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

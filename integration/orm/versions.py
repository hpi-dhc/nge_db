from datetime import datetime
from sqlalchemy import String, Text, DateTime
from integration.orm.base import Base
from sqlalchemy.orm import Mapped, mapped_column

class Version(Base):

    __tablename__ = "nge_version"
    source : Mapped[str] = mapped_column(String(100), nullable=False, primary_key=True)
    version: Mapped[str] = mapped_column(Text(), nullable=False)
    import_date: Mapped[datetime] = mapped_column(DateTime(), nullable=False)
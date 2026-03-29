import uuid
from datetime import datetime
from sqlalchemy import String, Text, Float, Boolean, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from database import Base
from config import settings


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    questionnaires: Mapped[list["Questionnaire"]] = relationship(back_populates="project", cascade="all, delete")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(512))
    file_type: Mapped[str] = mapped_column(String(32))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete")


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"))
    content: Mapped[str] = mapped_column(Text)          # sentence (embedded for search)
    window_content: Mapped[str | None] = mapped_column(Text, nullable=True)  # surrounding window (sent to LLM)
    page: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[list] = mapped_column(Vector(settings.embed_dim))
    document: Mapped["Document"] = relationship(back_populates="chunks")


class Questionnaire(Base):
    __tablename__ = "questionnaires"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(512))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    questions: Mapped[list["Question"]] = relationship(back_populates="questionnaire", cascade="all, delete")
    project: Mapped["Project | None"] = relationship(back_populates="questionnaires")


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    questionnaire_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questionnaires.id"))
    seq: Mapped[int] = mapped_column(Integer)
    question_text: Mapped[str] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_cell: Mapped[str | None] = mapped_column(String(32), nullable=True)
    answer: Mapped["Answer"] = relationship(back_populates="question", uselist=False, cascade="all, delete")
    questionnaire: Mapped["Questionnaire"] = relationship(back_populates="questions")


class Answer(Base):
    __tablename__ = "answers"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("questions.id"), unique=True)
    draft: Mapped[str | None] = mapped_column(Text)
    citations: Mapped[list | None] = mapped_column(JSON)
    confidence: Mapped[float | None] = mapped_column(Float)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=True)
    human_edit: Mapped[str | None] = mapped_column(Text)
    flag_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    question: Mapped["Question"] = relationship(back_populates="answer")


class AnswerLibraryEntry(Base):
    __tablename__ = "answer_library"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_embedding: Mapped[list] = mapped_column(Vector(settings.embed_dim))
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_questionnaire_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("questionnaires.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

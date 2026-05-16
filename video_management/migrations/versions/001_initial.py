"""Initial migration - create all tables."""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # users
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("username", sa.String(50), unique=True, index=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=True),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
        sa.Column("is_active", sa.Boolean(), default=True),
    )

    # printers
    op.create_table(
        "printers",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("moonraker_url", sa.String(255), nullable=False),
        sa.Column("api_key", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), default=True),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
    )

    # videos
    op.create_table(
        "videos",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("printer_id", sa.Integer(), sa.ForeignKey("printers.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("original_path", sa.String(512), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("fps", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
        sa.Column("modified_at", sa.DateTime(), nullable=True),
        sa.Column("moonraker_metadata_json", sa.JSON(), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("processing_options", sa.JSON(), nullable=True),
        sa.Column("metadata_status", sa.String(20), default="pending"),
        sa.Column("thumbnail_path", sa.String(512), nullable=True),
    )

    # processed_videos
    op.create_table(
        "processed_videos",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("processed_path", sa.String(512), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("format", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), default="pending"),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
    )

    # uploads
    op.create_table(
        "uploads",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("processed_video_id", sa.Integer(), sa.ForeignKey("processed_videos.id"), nullable=False),
        sa.Column("platform", sa.String(50), nullable=False),
        sa.Column("platform_video_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), default="pending"),
        sa.Column("upload_url", sa.String(512), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("upload_progress", sa.Integer(), nullable=True),
        sa.Column("platform_status", sa.String(50), nullable=True),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("retry_count", sa.Integer(), default=0),
        sa.Column("scheduled_for", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    # video_analytics
    op.create_table(
        "video_analytics",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("upload_id", sa.Integer(), sa.ForeignKey("uploads.id"), nullable=False),
        sa.Column("views", sa.Integer(), default=0),
        sa.Column("likes", sa.Integer(), default=0),
        sa.Column("comments", sa.Integer(), default=0),
        sa.Column("shares", sa.Integer(), default=0),
        sa.Column("collected_at", sa.DateTime(), default=sa.func.now()),
    )

    # platform_settings
    op.create_table(
        "platform_settings",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("platform", sa.String(50), unique=True, nullable=False),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), default=sa.func.now()),
    )

    # audio_tracks
    op.create_table(
        "audio_tracks",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("file_path", sa.String(512), nullable=False),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
    )

    # text_overlays
    op.create_table(
        "text_overlays",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("processed_video_id", sa.Integer(), sa.ForeignKey("processed_videos.id"), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("position_x", sa.Integer(), default=0),
        sa.Column("position_y", sa.Integer(), default=0),
        sa.Column("font_size", sa.Integer(), default=36),
        sa.Column("font_color", sa.String(20), default="white"),
        sa.Column("bg_color", sa.String(20), default="black@0.5"),
        sa.Column("start_time", sa.Float(), default=0.0),
        sa.Column("end_time", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
    )

    # video_audio
    op.create_table(
        "video_audio",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("processed_video_id", sa.Integer(), sa.ForeignKey("processed_videos.id"), nullable=False),
        sa.Column("audio_track_id", sa.Integer(), sa.ForeignKey("audio_tracks.id"), nullable=False),
        sa.Column("volume", sa.Float(), default=0.5),
        sa.Column("fade_in", sa.Float(), default=2.0),
        sa.Column("fade_out", sa.Float(), default=2.0),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
    )

    # upload_jobs
    op.create_table(
        "upload_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("upload_id", sa.Integer(), sa.ForeignKey("uploads.id"), nullable=False),
        sa.Column("status", sa.String(50), default="queued"),
        sa.Column("progress", sa.Integer(), default=0),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), default=0),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
    )

    # audit_log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
    )

    # zip_archives
    op.create_table(
        "zip_archives",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("printer_id", sa.Integer(), sa.ForeignKey("printers.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("original_path", sa.String(512), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("modified_at", sa.DateTime(), nullable=True),
        sa.Column("moonraker_metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), default=sa.func.now()),
    )


def downgrade():
    op.drop_table("zip_archives")
    op.drop_table("audit_log")
    op.drop_table("upload_jobs")
    op.drop_table("video_audio")
    op.drop_table("text_overlays")
    op.drop_table("audio_tracks")
    op.drop_table("platform_settings")
    op.drop_table("video_analytics")
    op.drop_table("uploads")
    op.drop_table("processed_videos")
    op.drop_table("videos")
    op.drop_table("printers")
    op.drop_table("users")

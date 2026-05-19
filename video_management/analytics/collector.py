"""Analytics collection and synchronization for video management system."""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from database.models import Upload, VideoAnalytics

logger = logging.getLogger(__name__)


class AnalyticsCollector:
    """Collects and synchronizes video analytics from YouTube and TikTok."""

    def __init__(
        self,
        db_session: Session,
        youtube_uploader: Any,
        tiktok_uploader: Any,
    ) -> None:
        """Initialize the analytics collector.

        Args:
            db_session: SQLAlchemy database session
            youtube_uploader: YouTube uploader instance
            tiktok_uploader: TikTok uploader instance
        """
        self.db_session = db_session
        self.youtube_uploader = youtube_uploader
        self.tiktok_uploader = tiktok_uploader
        logger.info("AnalyticsCollector initialized")

    def collect_youtube_analytics(
        self,
        upload_id: int,
        platform_video_id: str,
    ) -> Optional[VideoAnalytics]:
        """Collect analytics from YouTube for a specific video.

        Args:
            upload_id: Internal upload ID
            platform_video_id: YouTube video ID

        Returns:
            Created VideoAnalytics record or None on failure
        """
        logger.info(
            f"Collecting YouTube analytics for upload_id={upload_id}, "
            f"video_id={platform_video_id}"
        )

        try:
            if not hasattr(self.youtube_uploader, "get_video_analytics"):
                logger.warning(
                    "YouTube uploader does not support analytics collection"
                )
                return None

            data = self.youtube_uploader.get_video_analytics(platform_video_id)

            if not data:
                logger.warning(
                    f"No analytics data returned for YouTube video {platform_video_id}"
                )
                return None

            analytics = VideoAnalytics(
                upload_id=upload_id,
                views=data.get("views", 0),
                likes=data.get("likes", 0),
                comments=data.get("comments", 0),
                shares=data.get("shares", 0),
                collected_at=datetime.utcnow(),
            )

            self.db_session.add(analytics)
            self.db_session.commit()

            logger.info(
                f"Stored YouTube analytics for upload_id={upload_id}: "
                f"views={analytics.views}, likes={analytics.likes}, "
                f"comments={analytics.comments}"
            )

            return analytics

        except Exception:
            logger.exception(
                f"Failed to collect YouTube analytics for upload_id={upload_id}"
            )
            self.db_session.rollback()
            return None

    def collect_tiktok_analytics(
        self,
        upload_id: int,
        platform_video_id: str,
    ) -> Optional[VideoAnalytics]:
        """Collect analytics from TikTok for a specific video.

        Args:
            upload_id: Internal upload ID
            platform_video_id: TikTok video ID

        Returns:
            Created VideoAnalytics record or None on failure
        """
        logger.info(
            f"Collecting TikTok analytics for upload_id={upload_id}, "
            f"video_id={platform_video_id}"
        )

        try:
            if not hasattr(self.tiktok_uploader, "get_video_analytics"):
                logger.warning(
                    "TikTok uploader does not support analytics collection"
                )
                return None

            data = self.tiktok_uploader.get_video_analytics(platform_video_id)

            if not data:
                logger.warning(
                    f"No analytics data returned for TikTok video {platform_video_id}"
                )
                return None

            analytics = VideoAnalytics(
                upload_id=upload_id,
                views=data.get("views", 0),
                likes=data.get("likes", 0),
                comments=data.get("comments", 0),
                shares=data.get("shares", 0),
                collected_at=datetime.utcnow(),
            )

            self.db_session.add(analytics)
            self.db_session.commit()

            logger.info(
                f"Stored TikTok analytics for upload_id={upload_id}: "
                f"views={analytics.views}, likes={analytics.likes}, "
                f"comments={analytics.comments}"
            )

            return analytics

        except Exception:
            logger.exception(
                f"Failed to collect TikTok analytics for upload_id={upload_id}"
            )
            self.db_session.rollback()
            return None

    def sync_all_analytics(self) -> Dict[str, Any]:
        """Synchronize analytics for all active uploads.

        Returns:
            Dictionary with sync results
        """
        logger.info("Starting full analytics sync")

        results: Dict[str, Any] = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
        }

        try:
            active_uploads = (
                self.db_session.query(Upload)
                .filter(
                    Upload.status.in_(["completed", "published", "active"]),
                    Upload.platform_video_id.isnot(None),
                )
                .all()
            )

            results["total"] = len(active_uploads)

            for upload in active_uploads:
                detail: Dict[str, Any] = {
                    "upload_id": upload.id,
                    "platform": upload.platform,
                    "platform_video_id": upload.platform_video_id,
                    "status": "pending",
                }

                try:
                    if upload.platform.lower() == "youtube":
                        analytics = self.collect_youtube_analytics(
                            upload.id,
                            upload.platform_video_id,
                        )
                    elif upload.platform.lower() == "tiktok":
                        analytics = self.collect_tiktok_analytics(
                            upload.id,
                            upload.platform_video_id,
                        )
                    else:
                        logger.warning(
                            f"Unsupported platform '{upload.platform}' for "
                            f"upload_id={upload.id}"
                        )
                        detail["status"] = "skipped"
                        results["skipped"] += 1
                        results["details"].append(detail)
                        continue

                    if analytics:
                        detail["status"] = "success"
                        detail["views"] = analytics.views
                        detail["likes"] = analytics.likes
                        detail["comments"] = analytics.comments
                        results["success"] += 1
                    else:
                        detail["status"] = "failed"
                        results["failed"] += 1

                except Exception:
                    logger.exception(
                        f"Error syncing analytics for upload_id={upload.id}"
                    )
                    detail["status"] = "failed"
                    results["failed"] += 1

                results["details"].append(detail)

            logger.info(
                f"Analytics sync complete: {results['success']} succeeded, "
                f"{results['failed']} failed, {results['skipped']} skipped"
            )

            return results

        except Exception:
            logger.exception("Failed to sync all analytics")
            return results

    def get_analytics_summary(self, days: int = 30) -> Dict[str, Any]:
        """Get summary statistics for the dashboard.

        Args:
            days: Number of days to include in summary

        Returns:
            Dictionary with summary statistics
        """
        logger.info(f"Getting analytics summary for last {days} days")

        try:
            since = datetime.utcnow() - timedelta(days=days)

            latest_analytics = (
                self.db_session.query(
                    VideoAnalytics.upload_id,
                    func.max(VideoAnalytics.collected_at).label("latest_date"),
                )
                .filter(VideoAnalytics.collected_at >= since)
                .group_by(VideoAnalytics.upload_id)
                .subquery()
            )

            summary = (
                self.db_session.query(
                    func.sum(VideoAnalytics.views).label("total_views"),
                    func.sum(VideoAnalytics.likes).label("total_likes"),
                    func.sum(VideoAnalytics.comments).label("total_comments"),
                    func.sum(VideoAnalytics.shares).label("total_shares"),
                    func.count(func.distinct(VideoAnalytics.upload_id)).label(
                        "total_videos"
                    ),
                )
                .join(
                    latest_analytics,
                    (
                        VideoAnalytics.upload_id
                        == latest_analytics.c.upload_id
                    )
                    & (
                        VideoAnalytics.collected_at
                        == latest_analytics.c.latest_date
                    ),
                )
                .first()
            )

            daily = (
                self.db_session.query(
                    func.date(VideoAnalytics.collected_at).label("date"),
                    func.sum(VideoAnalytics.views).label("views"),
                    func.sum(VideoAnalytics.likes).label("likes"),
                )
                .filter(VideoAnalytics.collected_at >= since)
                .group_by(func.date(VideoAnalytics.collected_at))
                .order_by("date")
                .all()
            )

            result: Dict[str, Any] = {
                "period_days": days,
                "total_views": summary.total_views or 0,
                "total_likes": summary.total_likes or 0,
                "total_comments": summary.total_comments or 0,
                "total_shares": summary.total_shares or 0,
                "total_videos": summary.total_videos or 0,
                "daily_breakdown": [
                    {
                        "date": str(d.date),
                        "views": d.views or 0,
                        "likes": d.likes or 0,
                    }
                    for d in daily
                ],
            }

            logger.info(
                f"Analytics summary: {result['total_views']} total views"
            )
            return result

        except Exception:
            logger.exception("Failed to get analytics summary")
            return {
                "period_days": days,
                "total_views": 0,
                "total_likes": 0,
                "total_comments": 0,
                "total_shares": 0,
                "total_videos": 0,
                "daily_breakdown": [],
            }

    def get_platform_comparison(self) -> Dict[str, Any]:
        """Compare YouTube vs TikTok performance.

        Returns:
            Dictionary with platform comparison data
        """
        logger.info("Getting platform comparison")

        try:
            latest_dates = (
                self.db_session.query(
                    VideoAnalytics.upload_id,
                    func.max(VideoAnalytics.collected_at).label("latest_date"),
                )
                .group_by(VideoAnalytics.upload_id)
                .subquery()
            )

            platform_stats = (
                self.db_session.query(
                    Upload.platform,
                    func.sum(VideoAnalytics.views).label("total_views"),
                    func.sum(VideoAnalytics.likes).label("total_likes"),
                    func.sum(VideoAnalytics.comments).label("total_comments"),
                    func.sum(VideoAnalytics.shares).label("total_shares"),
                    func.count(func.distinct(Upload.id)).label("video_count"),
                    func.avg(VideoAnalytics.views).label("avg_views"),
                    func.avg(VideoAnalytics.likes).label("avg_likes"),
                )
                .join(VideoAnalytics, Upload.id == VideoAnalytics.upload_id)
                .join(
                    latest_dates,
                    (
                        VideoAnalytics.upload_id
                        == latest_dates.c.upload_id
                    )
                    & (
                        VideoAnalytics.collected_at
                        == latest_dates.c.latest_date
                    ),
                )
                .group_by(Upload.platform)
                .all()
            )

            comparison: Dict[str, Any] = {
                "platforms": {},
                "totals": {
                    "total_views": 0,
                    "total_likes": 0,
                    "total_comments": 0,
                    "total_shares": 0,
                    "total_videos": 0,
                },
            }

            for stat in platform_stats:
                platform_data: Dict[str, Any] = {
                    "total_views": stat.total_views or 0,
                    "total_likes": stat.total_likes or 0,
                    "total_comments": stat.total_comments or 0,
                    "total_shares": stat.total_shares or 0,
                    "video_count": stat.video_count or 0,
                    "avg_views": round(stat.avg_views or 0, 2),
                    "avg_likes": round(stat.avg_likes or 0, 2),
                }

                comparison["platforms"][stat.platform] = platform_data

                comparison["totals"]["total_views"] += platform_data[
                    "total_views"
                ]
                comparison["totals"]["total_likes"] += platform_data[
                    "total_likes"
                ]
                comparison["totals"]["total_comments"] += platform_data[
                    "total_comments"
                ]
                comparison["totals"]["total_shares"] += platform_data[
                    "total_shares"
                ]
                comparison["totals"]["total_videos"] += platform_data[
                    "video_count"
                ]

            logger.info(
                f"Platform comparison: {len(comparison['platforms'])} platforms"
            )
            return comparison

        except Exception:
            logger.exception("Failed to get platform comparison")
            return {
                "platforms": {},
                "totals": {
                    "total_views": 0,
                    "total_likes": 0,
                    "total_comments": 0,
                    "total_shares": 0,
                    "total_videos": 0,
                },
            }

    def get_trending_videos(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get top performing videos based on views.

        Args:
            limit: Maximum number of videos to return

        Returns:
            List of video analytics dictionaries
        """
        logger.info(f"Getting top {limit} trending videos")

        try:
            latest_dates = (
                self.db_session.query(
                    VideoAnalytics.upload_id,
                    func.max(VideoAnalytics.collected_at).label("latest_date"),
                )
                .group_by(VideoAnalytics.upload_id)
                .subquery()
            )

            trending = (
                self.db_session.query(Upload, VideoAnalytics)
                .join(VideoAnalytics, Upload.id == VideoAnalytics.upload_id)
                .join(
                    latest_dates,
                    (
                        VideoAnalytics.upload_id
                        == latest_dates.c.upload_id
                    )
                    & (
                        VideoAnalytics.collected_at
                        == latest_dates.c.latest_date
                    ),
                )
                .order_by(desc(VideoAnalytics.views))
                .limit(limit)
                .all()
            )

            results: List[Dict[str, Any]] = []
            for upload, analytics in trending:
                results.append(
                    {
                        "upload_id": upload.id,
                        "platform": upload.platform,
                        "platform_video_id": upload.platform_video_id,
                        "title": upload.title,
                        "views": analytics.views,
                        "likes": analytics.likes,
                        "comments": analytics.comments,
                        "shares": analytics.shares,
                        "collected_at": analytics.collected_at.isoformat(),
                    }
                )

            logger.info(f"Found {len(results)} trending videos")
            return results

        except Exception:
            logger.exception("Failed to get trending videos")
            return []

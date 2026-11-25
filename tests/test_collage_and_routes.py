import io
import json
import shutil
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from watermark_app import create_app
from watermark_app.services.collage_engine import (
    MediaValidationError,
    compose_collage,
    layout_boxes,
)
from watermark_app.services.social_downloader import (
    SocialDownloadError,
    _download_format,
    _format_options,
)


class CollageLayoutTests(unittest.TestCase):
    def test_layouts_match_required_slot_geometry(self):
        self.assertEqual(layout_boxes(1, 1280, 720), [(0, 0, 1280, 720)])
        self.assertEqual(
            layout_boxes(2, 1280, 720),
            [(0, 0, 640, 720), (640, 0, 640, 720)],
        )
        self.assertEqual(
            layout_boxes(3, 1280, 720),
            [(0, 0, 640, 360), (640, 0, 640, 360), (0, 360, 1280, 360)],
        )
        self.assertEqual(
            layout_boxes(4, 1080, 1080),
            [
                (0, 0, 540, 540),
                (540, 0, 540, 540),
                (0, 540, 540, 540),
                (540, 540, 540, 540),
            ],
        )

    def test_layout_rejects_out_of_range_counts(self):
        for count in (0, 5):
            with self.subTest(count=count), self.assertRaises(MediaValidationError):
                layout_boxes(count, 1280, 720)

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "FFmpeg is required",
    )
    def test_mixed_video_and_image_collage_preserves_audio(self):
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        with tempfile.TemporaryDirectory() as temp:
            output_dir = Path(temp)
            video_path = output_dir / "source.mp4"
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=red:s=64x64:r=10",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:sample_rate=44100",
                    "-t",
                    "1",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    str(video_path),
                ],
                check=True,
                timeout=30,
            )
            image_path = output_dir / "still.png"
            Image.new("RGB", (32, 32), "blue").save(image_path)
            output_path = compose_collage(
                [video_path, image_path],
                output_dir,
                640,
                360,
                {
                    "title": "Mixed media",
                    "description": "Video and image",
                    "top_color": "#312e81",
                    "top_opacity": 200,
                    "bottom_color": "#0f172a",
                    "bottom_opacity": 220,
                },
            )
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration:stream=codec_type,width,height",
                    "-of",
                    "json",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            metadata = json.loads(result.stdout)
            self.assertTrue(
                any(
                    stream["codec_type"] == "video"
                    and stream["width"] == 640
                    and stream["height"] == 360
                    for stream in metadata["streams"]
                )
            )
            self.assertTrue(any(stream["codec_type"] == "audio" for stream in metadata["streams"]))
            self.assertLessEqual(float(metadata["format"]["duration"]), 30)

    def test_banner_overlay_builds_canvas_sized_rgba_asset(self):
        from watermark_app.services.banner_overlay import build_banner_overlay

        with tempfile.TemporaryDirectory() as temp:
            output_path = build_banner_overlay(
                640,
                360,
                Path(temp),
                "A title that fits",
                "Small description",
                "#123456",
                180,
                "#654321",
                220,
            )
            with Image.open(output_path) as overlay:
                self.assertEqual(overlay.size, (640, 360))
                self.assertEqual(overlay.mode, "RGBA")
                self.assertEqual(overlay.getpixel((0, 360 - 45)), (18, 52, 86, 180))
                self.assertEqual(overlay.getpixel((0, 359)), (101, 67, 33, 220))

    def test_social_formats_include_only_selectable_mp4_video(self):
        info = {
            "formats": [
                {"format_id": "video-only", "ext": "mp4", "vcodec": "h264", "acodec": "none", "height": 720},
                {"format_id": "muxed", "ext": "mp4", "vcodec": "h264", "acodec": "aac", "height": 360},
                {"format_id": "audio", "ext": "m4a", "vcodec": "none", "acodec": "aac"},
                {"format_id": "webm", "ext": "webm", "vcodec": "vp9", "acodec": "opus"},
            ]
        }
        options = _format_options(info)
        self.assertEqual(
            [item["format_id"] for item in options],
            ["video-only", "muxed"],
        )
        self.assertEqual(_download_format("video-only", info), "video-only+bestaudio/video-only")
        self.assertEqual(_download_format("muxed", info), "muxed")
        with self.assertRaises(SocialDownloadError):
            _download_format("injected-format", info)


class FlaskMediaRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.client = self.app.test_client()

    @staticmethod
    def image_upload(color, name):
        content = io.BytesIO()
        Image.new("RGB", (40, 30), color).save(content, format="PNG")
        content.seek(0)
        return content, name

    def test_home_and_health_endpoints(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Build a collage", response.data)
        self.assertEqual(self.client.get("/health").json, {"status": "ok"})

    def test_collage_requires_one_to_four_files(self):
        no_files = self.client.post("/collage", data={})
        self.assertEqual(no_files.status_code, 400)
        self.assertIn("one and four", no_files.json["error"])

        five_files = [
            (io.BytesIO(b"image"), f"file-{index}.png")
            for index in range(5)
        ]
        too_many = self.client.post(
            "/collage",
            data={"media": five_files},
            content_type="multipart/form-data",
        )
        self.assertEqual(too_many.status_code, 400)

    def test_image_collage_streams_output_and_cleans_temp_files(self):
        temp_root = Path(tempfile.gettempdir())
        before = set(temp_root.glob("watermark-collage-*"))
        response = self.client.post(
            "/collage",
            data={
                "media": [
                    self.image_upload("#ee2222", "left.png"),
                    self.image_upload("#2222ee", "right.png"),
                ],
                "title": "Title",
                "description": "Description",
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/jpeg")
        try:
            result = Image.open(io.BytesIO(response.get_data())).convert("RGB")
            self.assertEqual(result.size, (1280, 720))
            left = result.getpixel((200, 200))
            right = result.getpixel((1000, 200))
            self.assertGreater(left[0], left[2])
            self.assertGreater(right[2], right[0])
            self.assertTrue(all(channel >= 245 for channel in result.getpixel((1, 1))))
            self.assertTrue(all(channel >= 245 for channel in result.getpixel((641, 1))))
        finally:
            response.close()
        self.assertFalse(set(temp_root.glob("watermark-collage-*")) - before)

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "FFmpeg is required",
    )
    def test_mixed_media_route_returns_downloadable_video_and_cleans_up(self):
        ffmpeg = shutil.which("ffmpeg")
        temp_root = Path(tempfile.gettempdir())
        before = set(temp_root.glob("watermark-collage-*"))
        with tempfile.TemporaryDirectory() as source_dir:
            video_path = Path(source_dir) / "short.mp4"
            subprocess.run(
                [
                    ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=red:s=64x64:r=10",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:sample_rate=44100",
                    "-t",
                    "1",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    str(video_path),
                ],
                check=True,
                timeout=30,
            )
            with video_path.open("rb") as input_video:
                response = self.client.post(
                    "/collage",
                    data={
                        "media": [
                            (input_video, "short.mp4"),
                            self.image_upload("#2222ee", "still.png"),
                        ],
                        "title": "Mixed media",
                        "description": "Video and image",
                    },
                    content_type="multipart/form-data",
                )
        try:
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.mimetype, "video/mp4")
            self.assertIn("attachment;", response.headers["Content-Disposition"])
            self.assertGreater(len(response.get_data()), 0)
        finally:
            response.close()
        self.assertFalse(set(temp_root.glob("watermark-collage-*")) - before)

    def test_single_watermark_keeps_existing_flow_and_cleans_temp_files(self):
        temp_root = Path(tempfile.gettempdir())
        before = set(temp_root.glob("watermark-single-*"))
        response = self.client.post(
            "/watermark",
            data={"media": self.image_upload("#ffffff", "single.png"), "text": "Brand"},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertGreater(len(response.get_data()), 0)
        response.close()
        self.assertFalse(set(temp_root.glob("watermark-single-*")) - before)

    def test_social_inspection_rejects_non_https_or_non_allowlisted_urls(self):
        response = self.client.post(
            "/social/inspect",
            json={"url": "http://127.0.0.1/private"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("HTTPS", response.json["error"])

    def test_request_size_limit_returns_structured_error(self):
        self.app.config["MAX_CONTENT_LENGTH"] = 32
        response = self.client.post(
            "/social/inspect",
            json={"url": "x" * 100},
        )
        self.assertEqual(response.status_code, 413)
        self.assertIn("64 MB", response.json["error"])

    def test_social_inspection_returns_selectable_formats(self):
        import watermark_app.services.social_downloader as downloader

        fake_address = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
        fake_info = {
            "title": "Public media",
            "formats": [
                {"format_id": "video", "ext": "mp4", "vcodec": "h264", "acodec": "aac", "height": 720}
            ],
        }
        with (
            patch.object(downloader.socket, "getaddrinfo", return_value=fake_address),
            patch.object(downloader, "_extract_info", return_value=fake_info),
        ):
            response = self.client.post(
                "/social/inspect",
                json={"url": "https://youtu.be/example"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["title"], "Public media")
        self.assertEqual(response.json["formats"][0]["format_id"], "video")

    def test_social_download_cleans_temporary_output_after_response(self):
        from watermark_app.services.social_downloader import download_social_media

        with tempfile.TemporaryDirectory() as parent:
            temp_dir = tempfile.TemporaryDirectory(prefix="watermark-social-test-", dir=parent)
            download_path = Path(temp_dir.name) / "media.mp4"
            download_path.write_bytes(b"sample video")
            with patch(
                "watermark_app.routes.social.download_social_media",
                return_value=(temp_dir, download_path),
            ):
                response = self.client.post(
                    "/social/download",
                    json={"url": "https://youtu.be/example", "format_id": "best"},
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.get_data(), b"sample video")
                response.close()
            self.assertFalse(Path(temp_dir.name).exists())


if __name__ == "__main__":
    unittest.main()

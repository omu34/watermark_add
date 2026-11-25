from pathlib import Path
from tempfile import TemporaryDirectory

from flask import Response, send_file


def temporary_download(
    temporary_directory: TemporaryDirectory,
    path: Path,
    download_name: str,
    mimetype: str | None = None,
) -> Response:
    media_file = path.open("rb")
    try:
        response = send_file(
            media_file,
            as_attachment=True,
            download_name=download_name,
            mimetype=mimetype,
            conditional=False,
        )
    except Exception:
        media_file.close()
        temporary_directory.cleanup()
        raise

    response.direct_passthrough = False

    def cleanup() -> None:
        media_file.close()
        temporary_directory.cleanup()

    response.call_on_close(cleanup)
    return response

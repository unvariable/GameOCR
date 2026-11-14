"""Wayland birincil backend'i: xdg-desktop-portal + PipeWire/GStreamer.

KDE Plasma / Wayland ortamında oyun penceresini veya ekranı yakalar.
Kullanıcının seçimi KDE tarafından bir ``restore_token`` ile saklanır;
sonraki çalıştırmalarda diyalog tekrar açılmaz.

OpenCV tekerleğinde (`opencv-python-headless`) GStreamer desteği bulunmadığında
otomatik olarak sistemdeki `gst-launch-1.0` (`pipewiresrc ! videoconvert ! jpegenc ! fdsink`)
alt süreci üzerinden sıfır gecikmeli kare okuma yapar.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import threading
import time
from typing import Any

import cv2
import numpy as np
from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus

from ..config import CaptureConfig
from .base import CaptureBackend, CaptureError, Rect, crop_fraction

log = logging.getLogger(__name__)

PORTAL_BUS = "org.freedesktop.portal.Desktop"
PORTAL_PATH = "/org/freedesktop/portal/desktop"
SCREENCAST_IFACE = "org.freedesktop.portal.ScreenCast"
REQUEST_IFACE = "org.freedesktop.portal.Request"


def _opencv_has_gstreamer() -> bool:
    try:
        info = cv2.getBuildInformation()
        return "GStreamer:                   YES" in info
    except Exception:
        return False


class _GstPipeWireReader:
    """`opencv-python-headless` GStreamer içermediğinde `gst-launch-1.0` ile PipeWire akışı okur."""

    def __init__(self, node_id: int, pw_fd: int = -1) -> None:
        self.node_id = node_id
        self.pw_fd = pw_fd
        self._proc: subprocess.Popen[bytes] | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> bool:
        if not shutil.which("gst-launch-1.0"):
            log.error("Sistemde gst-launch-1.0 bulunamadı")
            return False

        cmd = ["gst-launch-1.0", "-q", "pipewiresrc"]
        pass_fds: tuple[int, ...] = ()
        if self.pw_fd >= 0:
            cmd.append(f"fd={self.pw_fd}")
            pass_fds = (self.pw_fd,)
        cmd.extend([
            f"path={self.node_id}",
            "do-timestamp=true",
            "keepalive-time=100",
            "resend-last=true",
            "!",
            "videoconvert",
            "!",
            "jpegenc",
            "quality=95",
            "!",
            "fdsink",
            "fd=1",
        ])

        log.info("gst-launch-1.0 PipeWire okuyucu başlatılıyor: %s", " ".join(cmd))
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
                pass_fds=pass_fds,
            )
        except Exception as exc:
            log.error("gst-launch-1.0 başlatılamadı: %s", exc)
            return False

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._reader_loop,
            name="GstPipeWireReader",
            daemon=True,
        )
        self._thread.start()
        return True

    def _reader_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        buf = bytearray()
        stdout = proc.stdout
        while not self._stop.is_set() and proc.poll() is None:
            try:
                chunk = stdout.read(65536)
            except Exception:
                break
            if not chunk:
                break
            buf.extend(chunk)
            eoi = buf.rfind(b"\xff\xd9")
            if eoi != -1:
                soi = buf.rfind(b"\xff\xd8", 0, eoi)
                if soi != -1:
                    jpg_bytes = bytes(buf[soi : eoi + 2])
                    del buf[: eoi + 2]
                    arr = np.frombuffer(jpg_bytes, dtype=np.uint8)
                    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if frame is not None and frame.size > 0:
                        with self._lock:
                            self._latest_frame = frame
                else:
                    del buf[: eoi + 2]
            elif len(buf) > 8 * 1024 * 1024:
                buf.clear()

    def is_opened(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def read(self) -> tuple[bool, np.ndarray | None]:
        with self._lock:
            if self._latest_frame is not None:
                return True, self._latest_frame
        return False, None

    def release(self) -> None:
        self._stop.set()
        if self._proc is not None:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None


class PortalBackend(CaptureBackend):
    name = "Portal (Wayland pencere/ekran)"
    captures_overlay = False

    def __init__(self, cfg: CaptureConfig) -> None:
        self.cfg = cfg
        self._lock = threading.Lock()
        self._cap: cv2.VideoCapture | None = None
        self._gst_reader: _GstPipeWireReader | None = None
        self._bus: MessageBus | None = None
        self._active_bus: MessageBus | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._pending_futures: dict[str, asyncio.Future] = {}
        self._session_path: str = ""
        self._pw_fd: int = -1
        self._node_id: int = 0
        self.restore_token: str = cfg.portal_restore_token
        self._frame_w: int = 1920
        self._frame_h: int = 1080
        self._last_frame: np.ndarray | None = None

    def is_open(self) -> bool:
        if self._cap is not None and self._cap.isOpened():
            return True
        if self._gst_reader is not None and self._gst_reader.is_opened():
            return True
        return False

    def cancel_pending(self) -> None:
        """Bekleyen bir Portal diyalog çağrısı varsa derhal (thread-safe) sonlandırır."""
        loop = self._loop
        bus = self._active_bus

        def _abort() -> None:
            for fut in list(self._pending_futures.values()):
                if not fut.done():
                    fut.cancel()
            if bus is not None:
                try:
                    bus.disconnect()
                except Exception:
                    pass

        if loop is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(_abort)
                return
            except Exception:
                pass
        _abort()

    # ------------------------------------------------------------------ #
    # DBus / Portal İletişimi
    # ------------------------------------------------------------------ #
    def open(self) -> None:
        """Portal oturumu açar ve PipeWire video yakalamayı başlatır."""
        with self._lock:
            if self.is_open():
                return

            log.info("Wayland Portal ScreenCast başlatılıyor (token=%s)...", self.restore_token or "yok")
            loop = asyncio.new_event_loop()
            self._loop = loop
            try:
                session_path, node_id, token, pw_fd, stream_size = loop.run_until_complete(
                    self._setup_portal_session()
                )
            except Exception as exc:
                try:
                    loop.close()
                except Exception:
                    pass
                self._loop = None
                raise CaptureError(f"Wayland Portal oturumu kurulamadı: {exc}") from exc

            self._session_path = session_path
            self._node_id = node_id
            self._pw_fd = pw_fd
            if stream_size[0] > 0 and stream_size[1] > 0:
                self._frame_w, self._frame_h = stream_size
            if token:
                self.restore_token = token
                self.cfg.portal_restore_token = token

            if _opencv_has_gstreamer():
                if self._pw_fd >= 0:
                    gst_pipeline = (
                        f"pipewiresrc fd={self._pw_fd} path={self._node_id} do-timestamp=true "
                        f"keepalive-time=100 resend-last=true ! "
                        f"videoconvert ! video/x-raw,format=BGR ! appsink drop=true max-buffers=1"
                    )
                else:
                    gst_pipeline = (
                        f"pipewiresrc path={self._node_id} do-timestamp=true "
                        f"keepalive-time=100 resend-last=true ! "
                        f"videoconvert ! video/x-raw,format=BGR ! appsink drop=true max-buffers=1"
                    )
                log.info("OpenCV GStreamer boru hattı açılıyor: %s", gst_pipeline)
                self._cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
                if not self._cap.isOpened():
                    self._cap = None

            if self._cap is None:
                reader = _GstPipeWireReader(node_id=self._node_id, pw_fd=self._pw_fd)
                if not reader.start():
                    self._cleanup_unlocked()
                    raise CaptureError("PipeWire GStreamer okuyucusu başlatılamadı")
                self._gst_reader = reader

            # İlk kareyi oku ve doğrula
            for _ in range(40):
                ret, frame = self._read_raw_frame()
                if ret and frame is not None and frame.size > 0:
                    self._frame_h, self._frame_w = frame.shape[:2]
                    self._last_frame = frame
                    log.info("PipeWire akışı bağlandı. Çözünürlük: %dx%d", self._frame_w, self._frame_h)
                    return
                time.sleep(0.05)

            log.warning(
                "PipeWire akışından henüz ilk kare gelmedi; arka planda bekleniyor (%dx%d)",
                self._frame_w,
                self._frame_h,
            )

    def _read_raw_frame(self) -> tuple[bool, np.ndarray | None]:
        if self._cap is not None:
            return self._cap.read()
        if self._gst_reader is not None:
            return self._gst_reader.read()
        return False, None

    async def _setup_portal_session(self) -> tuple[str, int, str, int, tuple[int, int]]:
        bus = await MessageBus(bus_type=BusType.SESSION, negotiate_unix_fd=True).connect()
        self._bus = bus
        self._active_bus = bus

        try:
            # DBus Match Rule: Portal Request Response sinyallerini dinle
            await bus.call(Message(
                destination="org.freedesktop.DBus",
                path="/org/freedesktop/DBus",
                interface="org.freedesktop.DBus",
                member="AddMatch",
                signature="s",
                body=[f"type='signal',interface='{REQUEST_IFACE}',member='Response'"],
            ))

            early_responses: dict[str, Any] = {}
            pending_futures = self._pending_futures
            pending_futures.clear()

            def on_dbus_signal(msg: Message) -> None:
                if msg.member == "Response" and msg.path:
                    if msg.path in pending_futures:
                        fut = pending_futures[msg.path]
                        if not fut.done():
                            fut.set_result(msg.body)
                    else:
                        early_responses[msg.path] = msg.body

            bus.add_message_handler(on_dbus_signal)

            async def wait_request(req_path: str, timeout: float) -> Any:
                if req_path in early_responses:
                    return early_responses.pop(req_path)
                fut = asyncio.get_running_loop().create_future()
                pending_futures[req_path] = fut
                return await asyncio.wait_for(fut, timeout=timeout)

            token_counter = int(time.time() * 1000) % 1_000_000_000

            # 1. CreateSession
            create_reply = await bus.call(Message(
                destination=PORTAL_BUS,
                path=PORTAL_PATH,
                interface=SCREENCAST_IFACE,
                member="CreateSession",
                signature="a{sv}",
                body=[{
                    "session_handle_token": Variant("s", f"gameocr_sess_{token_counter}"),
                    "handle_token": Variant("s", f"gameocr_req_{token_counter}_1"),
                }],
            ))
            req_path_1 = create_reply.body[0]
            body_1 = await wait_request(req_path_1, timeout=10.0)
            resp_code, results = body_1[0], body_1[1]
            if resp_code != 0:
                raise CaptureError(f"CreateSession reddedildi: kod {resp_code}")

            session_handle = results["session_handle"].value

            # 2. SelectSources
            # types: 3 = 1 | 2 (Monitor ve Window desteklenir, kullanıcı seçebilir)
            options_2: dict[str, Variant] = {
                "types": Variant("u", 3),
                "multiple": Variant("b", False),
                "cursor_mode": Variant("u", 1),   # Gizli imleç
                "persist_mode": Variant("u", 2),  # İzin iptal edilene kadar kalıcı
                "handle_token": Variant("s", f"gameocr_req_{token_counter}_2"),
            }
            if self.restore_token:
                options_2["restore_token"] = Variant("s", self.restore_token)

            select_reply = await bus.call(Message(
                destination=PORTAL_BUS,
                path=PORTAL_PATH,
                interface=SCREENCAST_IFACE,
                member="SelectSources",
                signature="oa{sv}",
                body=[session_handle, options_2],
            ))
            req_path_2 = select_reply.body[0]
            body_2 = await wait_request(req_path_2, timeout=30.0)
            if body_2[0] != 0:
                raise CaptureError(f"SelectSources iptal edildi veya reddedildi: kod {body_2[0]}")

            # 3. Start (KDE / GNOME pencere seçici diyalog penceresini ekrana getirir)
            log.info("Wayland Portal pencere seçici diyaloğu açılıyor (Start)...")
            start_reply = await bus.call(Message(
                destination=PORTAL_BUS,
                path=PORTAL_PATH,
                interface=SCREENCAST_IFACE,
                member="Start",
                signature="osa{sv}",
                body=[session_handle, "", {"handle_token": Variant("s", f"gameocr_req_{token_counter}_3")}],
            ))
            req_path_3 = start_reply.body[0]
            body_3 = await wait_request(req_path_3, timeout=120.0)
            if body_3[0] != 0:
                # Eğer kayıtlı restore_token geçersiz olduğu için reddedildiyse token'ı sıfırla
                if self.restore_token:
                    log.info("Kayıtlı restore_token geçersiz, sıfırlanıp pencere seçici tekrar açılıyor...")
                    self.restore_token = ""
                    self.cfg.portal_restore_token = ""
                    bus.disconnect()
                    self._bus = None
                    return await self._setup_portal_session()
                raise CaptureError(f"Pencere seçimi iptal edildi (kod {body_3[0]})")

            start_results = body_3[1]
            streams = start_results.get("streams", Variant("a(ua{sv})", [])).value
            if not streams:
                raise CaptureError("Portal hiçbir PipeWire akışı döndürmedi")

            node_id = int(streams[0][0])
            stream_size = (0, 0)
            if len(streams[0]) > 1 and isinstance(streams[0][1], dict):
                s_props = streams[0][1]
                if "size" in s_props:
                    sz_val = s_props["size"].value if hasattr(s_props["size"], "value") else s_props["size"]
                    if isinstance(sz_val, (list, tuple)) and len(sz_val) >= 2:
                        stream_size = (int(sz_val[0]), int(sz_val[1]))

            new_token = ""
            if "restore_token" in start_results:
                new_token = start_results["restore_token"].value

            # 4. OpenPipeWireRemote (dosya tanımlayıcısı al)
            pw_fd = -1
            try:
                pw_reply = await bus.call(Message(
                    destination=PORTAL_BUS,
                    path=PORTAL_PATH,
                    interface=SCREENCAST_IFACE,
                    member="OpenPipeWireRemote",
                    signature="oa{sv}",
                    body=[session_handle, {}],
                ))
                if pw_reply.message_type == MessageType.METHOD_RETURN and pw_reply.unix_fds:
                    pw_fd = os.dup(pw_reply.unix_fds[0])
                    log.info("PipeWire remote fd alındı: %d (node=%d)", pw_fd, node_id)
            except Exception as exc:
                log.debug("OpenPipeWireRemote isteğe bağlı çağrı atlandı: %s", exc)

            return session_handle, node_id, new_token, pw_fd, stream_size
        finally:
            self._active_bus = None

    # ------------------------------------------------------------------ #
    # Kare Yakalama
    # ------------------------------------------------------------------ #
    def grab_full(self) -> np.ndarray | None:
        with self._lock:
            ret, frame = self._read_raw_frame()
            if ret and frame is not None and frame.size > 0:
                self._frame_h, self._frame_w = frame.shape[:2]
                self._last_frame = frame
                return frame
            return self._last_frame

    def grab_roi(self, roi: list[float]) -> np.ndarray | None:
        full = self.grab_full()
        if full is None:
            return None
        return crop_fraction(full, roi)

    def source_geometry(self) -> Rect | None:
        """Pencere/akış çözünürlüğü."""
        with self._lock:
            return (0, 0, self._frame_w, self._frame_h)

    def forget_source(self) -> None:
        self.restore_token = ""
        self.cfg.portal_restore_token = ""

    def persist_state(self, cfg: CaptureConfig) -> None:
        if self.restore_token:
            cfg.portal_restore_token = self.restore_token

    def _cleanup_unlocked(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        if self._gst_reader is not None:
            try:
                self._gst_reader.release()
            except Exception:
                pass
            self._gst_reader = None
        if self._pw_fd >= 0:
            try:
                os.close(self._pw_fd)
            except OSError:
                pass
            self._pw_fd = -1
        if self._bus is not None:
            try:
                self._bus.disconnect()
            except Exception:
                pass
            self._bus = None
        if self._loop is not None:
            try:
                self._loop.close()
            except Exception:
                pass
            self._loop = None

    def close(self) -> None:
        self.cancel_pending()
        with self._lock:
            self._cleanup_unlocked()

import React, { useRef, useEffect, useState } from "react";
import Hls from "hls.js";
import { Dialog, IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";

export default function VideoPlayer({ url, onClose }) {
  const videoRef = useRef();
  const hlsRef = useRef(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);

  const cleanup = () => {
    if (hlsRef.current) {
      hlsRef.current.destroy();
      hlsRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.src = '';
    }
  };

  const initializePlayer = () => {
    if (!url || !videoRef.current) return;

    console.log('VideoPlayer - 開始載入 URL:', url);
    cleanup();

    // 如果是直播流 (m3u8)
    if (url.includes('/hls/') && url.endsWith('.m3u8')) {
      if (!Hls.isSupported()) {
        console.error('VideoPlayer - HLS not supported');
        return;
      }

      const hls = new Hls({
        debug: true,
        enableWorker: true,
        lowLatencyMode: true,
      });

      hls.on(Hls.Events.MANIFEST_LOADING, () => {
        console.log('VideoPlayer - Manifest loading');
      });

      hls.on(Hls.Events.MANIFEST_LOADED, (event, data) => {
        console.log('VideoPlayer - Manifest loaded:', data);
      });

      hls.on(Hls.Events.ERROR, (event, data) => {
        console.error('HLS Error:', data);
        if (data.fatal) {
          switch (data.type) {
            case Hls.ErrorTypes.NETWORK_ERROR:
              hls.startLoad();
              break;
            case Hls.ErrorTypes.MEDIA_ERROR:
              hls.recoverMediaError();
              break;
            default:
              cleanup();
              break;
          }
        }
      });

      try {
        hls.loadSource(url);
        hls.attachMedia(videoRef.current);
        hlsRef.current = hls;
      } catch (error) {
        console.error('HLS initialization error:', error);
      }
    } 
    // 如果是錄製的視頻文件
    else if (url.includes('/recordings/')) {
      try {
        let playUrl = url;
        console.log('Playing recorded video file:', playUrl);
        videoRef.current.src = playUrl;
        videoRef.current.load();
        videoRef.current.play().catch(e => {
          console.error('Video playback error:', e);
        });
      } catch (error) {
        console.error('Recorded video playback error:', error);
      }
    }
  };

  useEffect(() => {
    if (url) {
      setIsDialogOpen(true);
    }
  }, [url]);

  useEffect(() => {
    if (isDialogOpen && videoRef.current) {
      initializePlayer();
    }
  }, [isDialogOpen, url]);

  useEffect(() => {
    return cleanup;
  }, []);

  const handleClose = () => {
    setIsDialogOpen(false);
    cleanup();
    if (onClose) onClose();
  };

  return (
    <Dialog 
      open={isDialogOpen} 
      onClose={handleClose}
      fullWidth 
      maxWidth="md"
    >
      <div style={{ 
        position: "relative", 
        background: "#000",
        width: "100%",
        height: "calc(100vh - 64px)",
        maxHeight: "calc(100vh - 64px)",
      }}>
        <video
          ref={videoRef}
          style={{ 
            width: "100%", 
            height: "100%",
            objectFit: "contain" 
          }}
          controls
          autoPlay
          playsInline
        >
          不支援此格式
        </video>
        <IconButton
          style={{ 
            position: "absolute", 
            top: 8, 
            right: 8, 
            color: "#fff",
            backgroundColor: "rgba(0,0,0,0.5)" 
          }}
          onClick={handleClose}
        >
          <CloseIcon />
        </IconButton>
      </div>
    </Dialog>
  );
}
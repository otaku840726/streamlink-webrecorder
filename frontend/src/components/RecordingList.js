import React, { useEffect, useState } from "react";
import { Box, Typography, Table, TableHead, TableBody, TableRow, TableCell, Button } from "@mui/material";
import api from "../api";
import VideoPlayer from "./VideoPlayer";

export default function RecordingList({ task }) {
  const [recordings, setRecordings] = useState([]);
  const [playFile, setPlayFile] = useState(null);
  const [playUrl, setPlayUrl] = useState(null);
  const [isActive, setIsActive] = useState(false);

  // 載入錄影清單和當前錄影狀態
  const reload = async () => {
    setRecordings(await api.listRecordings(task.id));
    try {
      const active = await api.getActiveRecordings();
      setIsActive(active.includes(task.id));
    } catch {
      setIsActive(false);
    }
  };

  useEffect(() => {
    reload();
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, [task.id]);

  const handlePlay = (url, file) => {
    setPlayUrl(url);
    setPlayFile(file);
  };

  return (
    <Box sx={{ my: 2, overflowX: "auto" }}>
      <Typography variant="h6">
        錄影清單 - {task.name}
        {isActive && (
          <span style={{ color: "red", marginLeft: 8, fontWeight: "bold" }}>
            ● 錄影中
          </span>
        )}
        {/* HLS 直播按鈕（只要任務支援） */}
        {task.hls_enable && (
          <Button
            size="small"
            color="success"
            sx={{ ml: 2 }}
            onClick={() => handlePlay(`/hls/${task.id}/stream.m3u8`, "live")}
          >
            直播觀看
          </Button>
        )}
      </Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell sx={{ minWidth: 140 }}>檔案名稱</TableCell>
            <TableCell sx={{ minWidth: 80 }}>大小(MB)</TableCell>
            <TableCell sx={{ minWidth: 140 }}>錄影時間</TableCell>
            <TableCell sx={{ minWidth: 260 }}>操作</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {recordings.map((rec) => (
            <TableRow key={rec.file}>
              <TableCell>{rec.file}</TableCell>
              <TableCell>{(rec.size / 1024 / 1024).toFixed(1)}</TableCell>
              <TableCell>{new Date(rec.mtime).toLocaleString()}</TableCell>
              <TableCell>
                {/* 1. 正在錄影的 TS 可即時觀看 */}
                {isActive && rec.file.endsWith('.ts') && (
                  <Button
                    size="small"
                    color="secondary"
                    onClick={() => handlePlay(`/tasks/${task.id}/recordings/${rec.file}/live_mp4`, rec.file)}
                    sx={{ mr: 1 }}
                  >
                    即時觀看
                  </Button>
                )}
                {/* 2. 所有 TS 可「線上轉檔」點播 */}
                {rec.file.endsWith('.ts') && (
                  <Button
                    size="small"
                    onClick={() => handlePlay(`/tasks/${task.id}/recordings/${rec.file}/mp4`, rec.file)}
                    sx={{ mr: 1 }}
                  >
                    線上播放
                  </Button>
                )}
                {/* 3. MP4 檔直接播放 */}
                {rec.file.endsWith('.mp4') && (
                  <Button
                    size="small"
                    onClick={() => handlePlay(`/tasks/${task.id}/recordings/${rec.file}`, rec.file)}
                    sx={{ mr: 1 }}
                  >
                    播放
                  </Button>
                )}
                {/* 4. 通用下載 */}
                <Button
                  size="small"
                  color="primary"
                  href={`/tasks/${task.id}/recordings/${rec.file}`}
                  target="_blank"
                  sx={{ mr: 1 }}
                >
                  下載
                </Button>
                <Button
                  size="small"
                  color="error"
                  onClick={async () => {
                    if (window.confirm("確定要刪除這個錄影檔？")) {
                      await api.deleteRecording(task.id, rec.file);
                      reload();
                    }
                  }}
                >
                  刪除
                </Button>
                {playFile === rec.file && playUrl && (
                  <VideoPlayer
                    url={playUrl}
                    onClose={() => { setPlayFile(null); setPlayUrl(null); }}
                  />
                )}
                {/* 直播觀看專屬視窗 */}
                {playFile === "live" && playUrl && (
                  <VideoPlayer
                    url={playUrl}
                    onClose={() => { setPlayFile(null); setPlayUrl(null); }}
                  />
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

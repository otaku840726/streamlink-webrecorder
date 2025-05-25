import React, { useEffect, useState } from "react";
import { Box, Typography, Table, TableHead, TableBody, TableRow, TableCell, Button } from "@mui/material";
import api from "../api";

// 移除 VideoPlayer import，因為已經移到 App.js

export default function RecordingList({ task, onPlay }) {  // 添加 onPlay prop
  const [recordings, setRecordings] = useState([]);
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
  }, [task.id]);

  return (
    <Box sx={{ my: 2, overflowX: "auto" }}>
      <Typography variant="h6">
        錄影清單 - {task.name}
        {isActive && (
          <span style={{ color: "red", marginLeft: 8, fontWeight: "bold" }}>
            ● 錄影中
          </span>
        )}
        {isActive ? (
          <Button
            size="small"
            color="error"
            sx={{ ml: 2 }}
            onClick={async () => {
              if (window.confirm("確定要停止錄影？")) {
                await api.stopRecording(task.id);
                setTimeout(reload, 1000);
              }
            }}
          >
            停止錄影
          </Button>
        ) : (
          <Button
            size="small"
            color="success"
            sx={{ ml: 2 }}
            onClick={async () => {
              if (window.confirm("確定要重新開始錄影？")) {
                await api.updateTask({ ...task });
                setTimeout(reload, 1000);
              }
            }}
          >
            再錄製
          </Button>
        )}
        {task.hls_enable && (
          <Button
            size="small"
            color="success"
            sx={{ ml: 2 }}
            onClick={() => onPlay(`/hls/${task.id}/stream.m3u8`)}  // 使用傳入的 onPlay
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
                <Button
                  size="small"
                  onClick={() => {
                    // 構建完整的播放 URL
                    const baseUrl = `tasks/${task.id}/recordings/${rec.file}`;
                    const playUrl = rec.file.toLowerCase().endsWith('.ts') 
                      ? `${baseUrl}/mp4`  // 修正：使用 /mp4 而不是 /live_mp4
                      : baseUrl;
                    onPlay(playUrl);
                  }}
                >
                  播放
                </Button>
                {/* 恢復刪除按鈕 */}
                <Button
                  size="small"
                  color="error"
                  sx={{ ml: 1 }}
                  onClick={async () => {
                    if (window.confirm("確定要刪除這個檔案嗎？")) {
                      await api.deleteRecording(task.id, rec.file);
                      reload();  // 刪除後重新載入列表
                    }
                  }}
                >
                  刪除
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}
import React, { useEffect, useState } from "react";
import { Box, Typography, Table, TableHead, TableBody, TableRow, TableCell, Button } from "@mui/material";
import api from "../api";
import VideoPlayer from "./VideoPlayer";

export default function RecordingList({ task }) {
  const [recordings, setRecordings] = useState([]);
  const [playFile, setPlayFile] = useState(null);
  const [isActive, setIsActive] = useState(false);

  // 查詢錄影清單 + 錄影進行中
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

  const handleStop = async () => {
    if (window.confirm("確定要停止錄影？")) {
      await api.stopRecording(task.id);
      reload();
    }
  };

  return (
    <Box sx={{ my: 2, overflowX: "auto" }}>
      <Typography variant="h6">
        錄影清單 - {task.name}
        {isActive && (
          <>
            <span style={{ color: "red", marginLeft: 8, fontWeight: "bold" }}>
              ● 錄影中
            </span>
            <Button
              color="warning"
              variant="outlined"
              size="small"
              sx={{ ml: 2 }}
              onClick={handleStop}
            >
              停止錄影
            </Button>
          </>
        )}
      </Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell sx={{ minWidth: 140 }}>檔案名稱</TableCell>
            <TableCell sx={{ minWidth: 80 }}>大小(MB)</TableCell>
            <TableCell sx={{ minWidth: 140 }}>錄影時間</TableCell>
            <TableCell sx={{ minWidth: 160 }}>操作</TableCell>
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
                  onClick={() => setPlayFile(rec.file)}
                  sx={{ mr: 1 }}
                >
                  播放
                </Button>
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
                {playFile === rec.file && (
                  <VideoPlayer
                    url={`/tasks/${task.id}/recordings/${rec.file}`}
                    onClose={() => setPlayFile(null)}
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

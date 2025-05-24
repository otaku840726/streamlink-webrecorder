import React, { useEffect, useState } from "react";
import { Box, Typography, Table, TableHead, TableBody, TableRow, TableCell, Button } from "@mui/material";
import api from "../api";
import VideoPlayer from "./VideoPlayer";

export default function RecordingList({ task }) {
  const [recordings, setRecordings] = useState([]);
  const [playFile, setPlayFile] = useState(null);

  const reload = async () => {
    setRecordings(await api.listRecordings(task.id));
  };

  useEffect(() => {
    reload();
    const t = setInterval(reload, 5000);
    return () => clearInterval(t);
    // eslint-disable-next-line
  }, [task.id]);

  return (
    <Box sx={{ my: 2 }}>
      <Typography variant="h6">錄影清單 - {task.name}</Typography>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>檔案名稱</TableCell>
            <TableCell>大小(MB)</TableCell>
            <TableCell>錄影時間</TableCell>
            <TableCell>操作</TableCell>
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
                  撥放
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

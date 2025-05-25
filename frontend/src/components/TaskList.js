// src/components/TaskList.jsx
import React from "react";
import {
  Table, TableHead, TableRow, TableCell, TableBody, Button, Box,
} from "@mui/material";
import api from "../api";

export default function TaskList({ tasks, onSelectTask, onEditTask, onShowLogs, reload }) {
  return (
      <Box sx={{ my: 2, overflowX: "auto" }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ minWidth: 80 }}>名稱</TableCell>
              <TableCell sx={{ minWidth: 180 }}>URL</TableCell>
              <TableCell sx={{ minWidth: 80 }}>間隔(分鐘)</TableCell>
              <TableCell sx={{ minWidth: 100 }}>保存路徑</TableCell>
              <TableCell sx={{ minWidth: 180 }}>操作</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {tasks.map((t) => (
                <TableRow key={t.id}>
                  <TableCell>{t.name}</TableCell>
                  <TableCell sx={{ maxWidth: 180, wordBreak: "break-all" }}>{t.url}</TableCell>
                  <TableCell>{t.interval}</TableCell>
                  <TableCell>{t.save_dir}</TableCell>
                  <TableCell>
                    <Button size="small" onClick={() => onSelectTask(t)}>錄影</Button>
                    <Button size="small" onClick={() => onShowLogs(t)}>紀錄</Button>
                    <Button size="small" onClick={() => onEditTask(t)}>編輯</Button>
                    <Button
                        size="small"
                        color="error"
                        onClick={async () => {
                          if (window.confirm("確定要刪除這個任務？")) {
                            await api.deleteTask(t.id);
                            reload();
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

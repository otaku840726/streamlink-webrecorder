import React from "react";
import {
  Table, TableHead, TableRow, TableCell, TableBody, Button, Box,
} from "@mui/material";

export default function TaskList({ tasks, onSelectTask, onEditTask, onShowLogs, reload }) {
  return (
    <Box sx={{ my: 2 }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>名稱</TableCell>
            <TableCell>URL</TableCell>
            <TableCell>間隔(分鐘)</TableCell>
            <TableCell>保存路徑</TableCell>
            <TableCell>操作</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {tasks.map((t) => (
            <TableRow key={t.id}>
              <TableCell>{t.name}</TableCell>
              <TableCell sx={{ maxWidth: 250, wordBreak: "break-all" }}>{t.url}</TableCell>
              <TableCell>{t.interval}</TableCell>
              <TableCell>{t.save_dir}</TableCell>
              <TableCell>
                <Button size="small" onClick={() => onSelectTask(t)}>錄影</Button>
                <Button size="small" onClick={() => onShowLogs(t)}>紀錄</Button>
                <Button size="small" onClick={() => onEditTask(t)}>編輯</Button>
                <Button size="small" color="error" onClick={async () => {
                  if (window.confirm("確定要刪除這個任務？")) {
                    await fetch(`/tasks/${t.id}`, { method: "DELETE" });
                    reload();
                  }
                }}>刪除</Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}

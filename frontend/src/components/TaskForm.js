import React, { useState } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  TextField,
  DialogActions,
  Button,
} from "@mui/material";
import api from "../api";

export default function TaskForm({ open, task, onClose }) {
  const isEdit = !!task;
  const [form, setForm] = useState(
    task || {
      name: "",
      url: "",
      interval: 5,
      save_dir: "",
      params: "",
    }
  );

  const handleChange = (e) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  const handleSubmit = async () => {
    if (!form.name || !form.url || !form.interval || !form.save_dir) {
      alert("所有欄位皆必填！");
      return;
    }
    if (isEdit) {
      await api.updateTask({ ...form, id: task.id });
    } else {
      await api.createTask({ ...form, id: undefined });
    }
    onClose();
  };

  return (
    <Dialog open={open} onClose={onClose}>
      <DialogTitle>{isEdit ? "編輯任務" : "新增任務"}</DialogTitle>
      <DialogContent>
        <TextField
          autoFocus
          margin="dense"
          label="名稱"
          name="name"
          value={form.name}
          onChange={handleChange}
          fullWidth
        />
        <TextField
          margin="dense"
          label="Stream URL"
          name="url"
          value={form.url}
          onChange={handleChange}
          fullWidth
        />
        <TextField
          margin="dense"
          label="檢查間隔 (分鐘)"
          name="interval"
          type="number"
          value={form.interval}
          onChange={handleChange}
          fullWidth
        />
        <TextField
          margin="dense"
          label="保存路徑 (如 mychannel)"
          name="save_dir"
          value={form.save_dir}
          onChange={handleChange}
          fullWidth
        />
        <TextField
          margin="dense"
          label="Streamlink 參數（選填）"
          name="params"
          value={form.params}
          onChange={handleChange}
          fullWidth
          placeholder="例如 --retry-open 1 --retry-streams 10"
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>取消</Button>
        <Button onClick={handleSubmit} variant="contained">
          {isEdit ? "儲存" : "新增"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

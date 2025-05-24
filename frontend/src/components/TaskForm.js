import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  TextField,
  DialogActions,
  Button,
} from "@mui/material";
import api from "../api";

const defaultForm = {
  name: "",
  url: "",
  interval: 5,
  save_dir: "",
  params: "",
};

export default function TaskForm({ open, task, onClose }) {
  const [form, setForm] = useState(defaultForm);

  // 根據 props.task 及 open 狀態切換內容
  useEffect(() => {
    if (task) setForm(task);
    else setForm(defaultForm);
  }, [task, open]);

  const handleChange = (e) => {
    let { name, value } = e.target;
    if (name === "interval") value = parseInt(value, 10) || 1;
    setForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async () => {
    if (!form.name || !form.url || !form.interval || !form.save_dir) {
      alert("所有欄位皆必填！");
      return;
    }
    if (task && task.id) {
      // 編輯
      await api.updateTask({ ...form, id: task.id });
    } else {
      // 新增（不要帶 id）
      const { id, ...body } = form;
      await api.createTask(body);
    }
    onClose();
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{task ? "編輯任務" : "新增任務"}</DialogTitle>
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
          {task ? "儲存" : "新增"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

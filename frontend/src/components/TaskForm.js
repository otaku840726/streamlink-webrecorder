import React, { useState, useEffect } from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  TextField,
  DialogActions,
  Button,
  FormControlLabel,
  Checkbox
} from "@mui/material";
import api from "../api";

const defaultForm = {
  name: "",
  url: "",
  interval: 5,
  save_dir: "",
  params: "",
  hls_enable: false,      // <--- 新增
};

export default function TaskForm({ open, task, onClose }) {
  const [form, setForm] = useState(defaultForm);

  useEffect(() => {
    if (task) setForm({ ...defaultForm, ...task });
    else setForm(defaultForm);
  }, [task, open]);

  const handleChange = (e) => {
    let { name, value, type, checked } = e.target;
    if (type === "checkbox") value = checked;
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
          label="streamlink 參數 (選填)"
          name="params"
          value={form.params}
          onChange={handleChange}
          fullWidth
        />
        <FormControlLabel
          control={
            <Checkbox
              name="hls_enable"
              checked={!!form.hls_enable}
              onChange={handleChange}
              color="primary"
            />
          }
          label="啟用 HLS 串流（直播 m3u8，直播觀看專用）"
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>取消</Button>
        <Button onClick={handleSubmit}>儲存</Button>
      </DialogActions>
    </Dialog>
  );
}

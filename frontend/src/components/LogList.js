import React, { useEffect, useState } from "react";
import { Box, Typography, List, ListItem, ListItemText } from "@mui/material";
import api from "../api";

const eventColor = (event) => {
  if (event === "error") return "red";
  if (event === "end" || event === "mp4") return "green";
  if (event === "no_stream") return "gray";
  return "black";
};

export default function LogList({ task }) {
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    api.getLogs(task.id).then(setLogs);
    const t = setInterval(() => {
      api.getLogs(task.id).then(setLogs);
    }, 5000);
    return () => clearInterval(t);
  }, [task.id]);

  return (
    <Box sx={{ my: 2, overflowX: "auto" }}>
      <Typography variant="h6">執行紀錄 - {task.name}</Typography>
      <List dense>
        {logs.map((log, idx) => (
          <ListItem key={idx}>
            <ListItemText
              primary={
                <span style={{ color: eventColor(log.event), fontSize: 14 }}>
                  [{new Date(log.time).toLocaleString()}] {log.event}
                  {log.msg ? ` | ${log.msg}` : ""}
                </span>
              }
            />
          </ListItem>
        ))}
      </List>
    </Box>
  );
}

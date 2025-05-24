import React from "react";
import { Dialog, DialogContent, IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";

export default function VideoPlayer({ url, onClose }) {
  return (
    <Dialog open={!!url} onClose={onClose} maxWidth="md" fullWidth>
      <DialogContent>
        <video src={url} controls style={{ width: "100%" }} />
        <IconButton
          onClick={onClose}
          sx={{ position: "absolute", top: 8, right: 8 }}
        >
          <CloseIcon />
        </IconButton>
      </DialogContent>
    </Dialog>
  );
}

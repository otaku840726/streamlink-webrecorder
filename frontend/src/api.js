import axios from "axios";
const API = process.env.REACT_APP_API || "";

const api = {
  async listTasks() {
    const r = await axios.get(`${API}/tasks`);
    return r.data;
  },
  async createTask(task) {
    const r = await axios.post(`${API}/tasks`, task);
    return r.data;
  },
  async updateTask(task) {
    const r = await axios.put(`${API}/tasks/${task.id}`, task);
    return r.data;
  },
  async deleteTask(id) {
    await axios.delete(`${API}/tasks/${id}`);
  },
  async listRecordings(taskId) {
    const r = await axios.get(`${API}/tasks/${taskId}/recordings`);
    return r.data;
  },
  async deleteRecording(taskId, filename) {
    await axios.delete(`${API}/tasks/${taskId}/recordings/${filename}`);
  },
  async getLogs(taskId) {
    const r = await axios.get(`${API}/tasks/${taskId}/logs`);
    return r.data;
  },
};

export default api;

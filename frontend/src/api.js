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
    async stopRecording(taskId) {
        await axios.post(`${API}/tasks/${taskId}/stop`);
    },
    async getActiveRecordings() {
        const res = await axios.get(`${API}/tasks/active_recordings`);
        return res.data;
    },
    async listThumbnails(taskId, filename) {
        const r = await axios.get(`${API}/tasks/${taskId}/recordings/${filename}/thumbnails`);
        return r.data;
    },
    // 在 api 对象中添加以下方法
    async convertRecording(taskId, filename, quality) {
        const r = await axios.post(`${API}/tasks/${taskId}/recordings/${filename}/convert?quality=${quality}`);
        return r.data;
    },
    async getConversionStatus(taskKey) {
        // taskKey 存在就带 ?task_key=xxx，否则直接拉全量
        const url = taskKey
          ? `${API}/conversion_status?task_key=${encodeURIComponent(taskKey)}`
          : `${API}/conversion_status`;
        const r = await axios.get(url);
        return r.data;
    },      
};

export default api;

# 使用當前長效支援版 (LTS)
FROM node:20  

# 设置工作目录
WORKDIR /app/frontend

# 复制项目文件到容器中
COPY . /app/frontend

# 安装依赖
RUN npm install

# 暴露端口
EXPOSE 3000

# 啟動應用 (將 start 改為 run dev)
CMD ["npm", "run", "dev"]
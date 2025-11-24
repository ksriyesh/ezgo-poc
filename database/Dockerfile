FROM postgis/postgis:16-3.4

# Copy initialization script
COPY init-extensions.sh /docker-entrypoint-initdb.d/

# Make script executable
RUN chmod +x /docker-entrypoint-initdb.d/init-extensions.sh



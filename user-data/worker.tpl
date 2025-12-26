#!/bin/bash
set -e

exec > >(tee -a /var/log/user-data.log)
exec 2>&1

echo "Starting Worker setup at $(date)"

RANDOM_SERVER_ID=$((RANDOM % 1000 + 2))
echo "Using server-id: ${RANDOM_SERVER_ID}"

echo "Updating system packages"
apt-get update -y

echo "Installing MySQL Server"
DEBIAN_FRONTEND=noninteractive apt-get install -y mysql-server wget

echo "Starting MySQL service"
systemctl start mysql
systemctl enable mysql

echo "Configuring MySQL users"
mysql -u root <<'MYSQL_SETUP'
ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'Root123!';
CREATE USER 'app_user'@'%' IDENTIFIED BY 'Mehdi1603!';
GRANT ALL PRIVILEGES ON *.* TO 'app_user'@'%';
FLUSH PRIVILEGES;
MYSQL_SETUP

echo "Configuring MySQL for replication (read-only replica)"
cat >> /etc/mysql/mysql.conf.d/mysqld.cnf <<MYSQL_CONFIG
[mysqld]
server-id=${RANDOM_SERVER_ID}
relay-log=mysql-relay-bin
log-bin=mysql-bin
binlog-format=ROW
bind-address=0.0.0.0
read-only=1
MYSQL_CONFIG

echo "Restarting MySQL service"
systemctl restart mysql

sleep 10

MANAGER_HOST="__MANAGER_HOST__"
MAX_RETRIES=30
RETRY_COUNT=0

echo "Waiting for manager at ${MANAGER_HOST} to be ready..."
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if mysql -h ${MANAGER_HOST} -u replication_user -pRepl123! -e "SELECT 1;" &>/dev/null; then
        echo "Manager is ready!"
        break
    fi
    echo "Attempt $((RETRY_COUNT + 1))/$MAX_RETRIES: Manager not ready, waiting..."
    sleep 20
    RETRY_COUNT=$((RETRY_COUNT + 1))
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "ERROR: Manager never became ready"
    exit 1
fi

echo "Setting up replication from beginning of binlog..."
mysql -u root -pRoot123! <<REPLICATION_SETUP
STOP SLAVE;
RESET SLAVE ALL;
CHANGE MASTER TO
  MASTER_HOST='${MANAGER_HOST}',
  MASTER_USER='replication_user',
  MASTER_PASSWORD='Repl123!',
  MASTER_LOG_FILE='mysql-bin.000001',
  MASTER_LOG_POS=4;
START SLAVE;
REPLICATION_SETUP

sleep 5
echo "=== SLAVE STATUS ==="
mysql -u root -pRoot123! -e "SHOW SLAVE STATUS\G"

echo "Waiting for Sakila database to be replicated..."
MAX_RETRIES=60
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if mysql -u root -pRoot123! -e "USE sakila; SHOW TABLES;" &>/dev/null; then
        TABLE_COUNT=$(mysql -u root -pRoot123! -e "USE sakila; SHOW TABLES;" | wc -l)
        if [ "$TABLE_COUNT" -gt 10 ]; then
            echo "Sakila database replicated successfully with $TABLE_COUNT tables!"
            break
        fi
    fi
    echo "Attempt $((RETRY_COUNT + 1))/$MAX_RETRIES: Waiting for Sakila replication..."
    sleep 10
    RETRY_COUNT=$((RETRY_COUNT + 1))
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo "ERROR: Sakila database never replicated"
    exit 1
fi

echo "Installing sysbench"
apt-get install -y sysbench

echo "Running sysbench benchmark on Worker..."
sysbench /usr/share/sysbench/oltp_read_only.lua \
    --mysql-db=sakila \
    --mysql-user=app_user \
    --mysql-password=Mehdi1603! \
    run > /tmp/sysbench_results.txt 2>&1

echo "Sysbench benchmark completed"

touch /tmp/worker_setup_complete
echo "Worker setup completed at $(date)"
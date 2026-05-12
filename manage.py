"""命令行小工具：初始化数据库、添加用户。

用法：
  python manage.py initdb                           # 仅建表
  python manage.py adduser admin pwd teacher       # 新增教师账号
  python manage.py adduser 2024001 123 student 5   # 关联学生 ID=5 的学生账号
"""
import sys

from app.models import init_schema, query_one, execute
from app.auth import hash_password


def adduser(username, password, role, student_id=None):
    if query_one("SELECT id FROM users WHERE username=?", (username,)):
        print(f"用户名 {username} 已存在")
        return
    execute(
        "INSERT INTO users(username,password_hash,role,student_id) VALUES (?,?,?,?)",
        (username, hash_password(password), role,
         int(student_id) if student_id else None),
    )
    print(f"✓ 已创建用户 {username}（{role}）")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    init_schema()
    cmd = sys.argv[1]
    if cmd == "initdb":
        print("✓ 数据库已初始化")
    elif cmd == "adduser":
        adduser(*sys.argv[2:])
    else:
        print("未知命令")


if __name__ == "__main__":
    main()

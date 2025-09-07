import socket
import threading
import json
import time
import os
from flask import Flask, jsonify
import requests

# Create Flask app for health checks
app = Flask(__name__)

@app.route('/')
def health_check():
    return "Room Server is running"

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "rooms": len(rooms), "timestamp": time.time()})

def get_public_ip():
    """Get the public IP address of the host"""
    try:
        manual_ip = os.environ.get('PUBLIC_IP')
        if manual_ip:
            print(f"📡 Using PUBLIC_IP from environment: {manual_ip}")
            return manual_ip

        services = [
            'https://api.ipify.org',
            'https://checkip.amazonaws.com',
            'https://ident.me'
        ]
        for service in services:
            try:
                response = requests.get(service, timeout=5)
                if response.status_code == 200:
                    ip = response.text.strip()
                    print(f"📡 Public IP detected from {service}: {ip}")
                    return ip
            except Exception as e:
                print(f"⚠️  Failed to get IP from {service}: {e}")
                continue

        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        print(f"📡 Using hostname IP as fallback: {ip}")
        return ip
    except Exception as e:
        print(f"❌ Error getting public IP: {e}")
        return '0.0.0.0'

def run_room_server():
    host = '0.0.0.0'
    port = int(os.environ.get('UDP_PORT', 5000))

    server = RoomServer(host, port)
    if server.start():
        print(f"✅ Room server started on {host}:{port}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Shutting down server...")
            server.stop()
    else:
        print("❌ Failed to start server")

class RoomServer:
    def __init__(self, host='0.0.0.0', port=5000):
        self.host = host
        self.port = port
        self.rooms = {}
        self.socket = None
        self.running = False
        self.public_ip = get_public_ip()

    def start(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.running = True

            threads = [
                threading.Thread(target=self._receive_loop),
                threading.Thread(target=self._cleanup_loop)
            ]
            for t in threads:
                t.daemon = True
                t.start()

            print(f"✅ UDP Server bound to {self.host}:{self.port}")
            print(f"📡 Server public IP (for identity): {self.public_ip}")
            print(f"🏠 Current rooms: {len(self.rooms)}")
            return True
        except Exception as e:
            print(f"❌ Error starting server: {e}")
            return False

    def stop(self):
        self.running = False
        if self.socket:
            self.socket.close()
            print("🛑 Server stopped")

    def _receive_loop(self):
        while self.running:
            try:
                data, addr = self.socket.recvfrom(4096)
                self._handle_message(data, addr)
            except socket.error as e:
                if self.running:
                    print(f"⚠️  Socket error: {e}")
            except Exception as e:
                if self.running:
                    print(f"⚠️  Error receiving data: {e}")

    def _handle_message(self, data, addr):
        try:
            message = json.loads(data.decode())
            action = message.get('action')
            peer_id = message.get('peer_id')
            print(f"📨 Received {action} from {addr} (peer {peer_id})")

            if action == 'create_room':
                self._handle_create_room(message, addr)
            elif action == 'join_room':
                self._handle_join_room(message, addr)
            elif action == 'leave_room':
                self._handle_leave_room(message, addr)
            elif action == 'keepalive':
                self._handle_keepalive(message, addr)
            elif action == 'punch_request':
                self._handle_punch_request(message, addr)
            elif action == 'get_rooms':
                self._handle_get_rooms(message, addr)
            else:
                print(f"❓ Unknown action {action}")
        except json.JSONDecodeError:
            print(f"📨 Non-JSON data from {addr}")
        except Exception as e:
            print(f"⚠️ Error handling message: {e}")

    def _handle_create_room(self, message, addr):
        room_id = message['room_id']
        peer_id = message['peer_id']
        username = message['username']

        if room_id not in self.rooms:
            self.rooms[room_id] = {'members': {}, 'created_at': time.time()}

        self.rooms[room_id]['members'][peer_id] = {
            'username': username,
            'addr': addr,
            'last_seen': time.time(),
            'public_ip': addr[0],   # use actual client IP
            'public_port': addr[1]
        }

        response = {
            'action': 'room_created',
            'room_id': room_id,
            'status': 'success',
            'public_ip': addr[0],
            'public_port': addr[1]
        }
        self._send_message(response, addr)

        for pid, info in self.rooms[room_id]['members'].items():
            if pid != peer_id:
                notification = {
                    'action': 'peer_joined',
                    'room_id': room_id,
                    'peer_id': peer_id,
                    'username': username,
                    'public_ip': addr[0],
                    'public_port': addr[1]
                }
                self._send_message(notification, info['addr'])

        print(f"🏠 Room '{room_id}' created by {username} ({peer_id})")

    def _handle_join_room(self, message, addr):
        room_id = message['room_id']
        peer_id = message['peer_id']
        username = message['username']

        if room_id not in self.rooms:
            self.rooms[room_id] = {'members': {}, 'created_at': time.time()}

        self.rooms[room_id]['members'][peer_id] = {
            'username': username,
            'addr': addr,
            'last_seen': time.time(),
            'public_ip': addr[0],   # use actual client IP
            'public_port': addr[1]
        }

        print(f"Peer joined: {peer_id} ({username}) public_ip={addr[0]} public_port={addr[1]}")

        members = {}
        for pid, info in self.rooms[room_id]['members'].items():
            if pid != peer_id:
                members[pid] = {
                    'username': info['username'],
                    'public_ip': info['public_ip'],
                    'public_port': info['public_port']
                }

        response = {
            'action': 'room_joined',
            'room_id': room_id,
            'members': members,
            'status': 'success',
            'public_ip': addr[0],
            'public_port': addr[1]
        }
        self._send_message(response, addr)

        for pid, info in self.rooms[room_id]['members'].items():
            if pid != peer_id:
                notification = {
                    'action': 'peer_joined',
                    'room_id': room_id,
                    'peer_id': peer_id,
                    'username': username,
                    'public_ip': addr[0],
                    'public_port': addr[1]
                }
                self._send_message(notification, info['addr'])

        print(f"👤 {username} joined room '{room_id}'")

    def _handle_leave_room(self, message, addr):
        room_id = message['room_id']
        peer_id = message['peer_id']

        if room_id in self.rooms and peer_id in self.rooms[room_id]['members']:
            username = self.rooms[room_id]['members'][peer_id]['username']
            del self.rooms[room_id]['members'][peer_id]

            for pid, info in self.rooms[room_id]['members'].items():
                notification = {
                    'action': 'peer_left',
                    'room_id': room_id,
                    'peer_id': peer_id
                }
                self._send_message(notification, info['addr'])

            if not self.rooms[room_id]['members']:
                del self.rooms[room_id]
                print(f"🧹 Removed empty room '{room_id}'")

            print(f"👋 {username} left room '{room_id}'")

    def _handle_keepalive(self, message, addr):
        room_id = message['room_id']
        peer_id = message['peer_id']
        if room_id in self.rooms and peer_id in self.rooms[room_id]['members']:
            self.rooms[room_id]['members'][peer_id]['last_seen'] = time.time()
            self.rooms[room_id]['members'][peer_id]['addr'] = addr

    def _handle_punch_request(self, message, addr):
        room_id = message['room_id']
        target_peer = message['target_peer']
        source_peer = message['source_peer']

        if room_id in self.rooms and target_peer in self.rooms[room_id]['members']:
            target_addr = self.rooms[room_id]['members'][target_peer]['addr']
            relay_msg = {
                'action': 'punch_request',
                'room_id': room_id,
                'source_peer': source_peer,
                'source_public_ip': addr[0],
                'source_public_port': addr[1]
            }
            self._send_message(relay_msg, target_addr)
            print(f"🔁 Relayed punch {source_peer} -> {target_peer}")

    def _handle_get_rooms(self, message, addr):
        room_list = {}
        for room_id, room_info in self.rooms.items():
            room_list[room_id] = {
                'member_count': len(room_info['members']),
                'created_at': room_info.get('created_at', 0)
            }
        response = {'action': 'room_list', 'rooms': room_list}
        self._send_message(response, addr)

    def _send_message(self, message, addr):
        try:
            data = json.dumps(message).encode()
            self.socket.sendto(data, addr)
        except Exception as e:
            print(f"⚠️ Send error to {addr}: {e}")

    def _cleanup_loop(self):
        while self.running:
            try:
                now = time.time()
                rooms_to_remove = []
                for room_id, room_info in list(self.rooms.items()):
                    stale = [pid for pid, info in room_info['members'].items() if now - info['last_seen'] > 60]
                    for pid in stale:
                        username = room_info['members'][pid]['username']
                        del room_info['members'][pid]
                        print(f"🧹 Removed stale peer {username} from '{room_id}'")
                    if not room_info['members']:
                        rooms_to_remove.append(room_id)
                for r in rooms_to_remove:
                    del self.rooms[r]
                    print(f"🧹 Removed empty room '{r}'")
            except Exception as e:
                print(f"⚠️ Cleanup error: {e}")
            time.sleep(30)

if __name__ == "__main__":
    from threading import Thread

    print("🚀 Starting Room Server...")
    print(f"🌐 Flask port: {os.environ.get('FLASK_PORT', 5001)}")
    print(f"📡 UDP port: {os.environ.get('UDP_PORT', 5000)}")

    udp_thread = Thread(target=run_room_server, daemon=True)
    udp_thread.start()

    flask_port = int(os.environ.get('FLASK_PORT', 5001))
    print(f"✅ Server started! Health: http://localhost:{flask_port}/health")

    app.run(host='0.0.0.0', port=flask_port, debug=False)

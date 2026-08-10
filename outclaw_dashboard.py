#!/usr/bin/env python3
"""
outclaw_dashboard.py - Real-Time Web Dashboard for OutClaw Swarm

A lightweight Flask-based dashboard to monitor:
- All connected devices (penguin, moto4, a9)
- Message queues and sync status
- Citation analysis results
- Multi-model consensus votes
- Pattern learning progress

Usage:
    python3 outclaw_dashboard.py
    
Then open: http://localhost:5000
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict

# Try to import Flask, but make it optional for non-web use
try:
    from flask import Flask, render_template_string, jsonify, request
    HAS_FLASK = True
except ImportError:
    HAS_FLASK = False
    print("Flask not installed. Web dashboard disabled.")
    print("Install with: pip install flask")

# Import OutClaw components
sys.path.insert(0, str(Path(__file__).parent))

try:
    from outclaw_learner import OutClawBrain, PatternLearner, SwarmIntelligence
    HAS_LEARNER = True
except ImportError:
    HAS_LEARNER = False

try:
    from outclaw_semantic import SeedRegistry
    HAS_SEMANTIC = True
except ImportError:
    HAS_SEMANTIC = False


class SwarmMonitor:
    """Monitors the OutClaw swarm across all devices."""
    
    def __init__(self, sync_bus_path: str = None):
        self.sync_bus_path = Path(sync_bus_path or Path.home() / '.outclaw' / 'sync_bus')
        self.brain = OutClawBrain() if HAS_LEARNER else None
        self.last_update = datetime.now()
        
    def get_device_status(self) -> Dict[str, Any]:
        """Get status of all devices in the swarm."""
        status = {}
        
        for device in ['penguin', 'moto4', 'a9']:
            device_path = self.sync_bus_path / device
            
            if not device_path.exists():
                status[device] = {
                    'online': False,
                    'error': 'Path does not exist',
                }
                continue
            
            # Count messages
            incoming = list((device_path / 'incoming').glob('*.json'))
            outgoing = list((device_path / 'outgoing').glob('*.json'))
            archive = list((device_path / 'archive').glob('*.json'))
            
            # Get latest message
            latest = None
            for f in sorted((device_path / 'archive').glob('*.json'), reverse=True):
                try:
                    with open(f, 'r') as file:
                        msg = json.load(file)
                    latest = {
                        'id': msg.get('id', 'unknown'),
                        'type': msg.get('type', 'unknown'),
                        'timestamp': msg.get('timestamp', 'unknown'),
                    }
                    break
                except (json.JSONDecodeError, IOError):
                    continue
            
            # Check identity file
            identity_path = device_path / 'identity.json'
            identity = {}
            if identity_path.exists():
                try:
                    with open(identity_path, 'r') as f:
                        identity = json.load(f)
                except (json.JSONDecodeError, IOError):
                    pass
            
            status[device] = {
                'online': True,
                'identity': identity,
                'queues': {
                    'incoming': len(incoming),
                    'outgoing': len(outgoing),
                    'archive': len(archive),
                },
                'latest_message': latest,
                'last_active': datetime.now().isoformat(),
            }
        
        return status
    
    def get_message_history(self, device: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent message history for a device."""
        archive_path = self.sync_bus_path / device / 'archive'
        
        if not archive_path.exists():
            return []
        
        messages = []
        for f in sorted(archive_path.glob('*.json'), reverse=True)[:limit]:
            try:
                with open(f, 'r') as file:
                    msg = json.load(file)
                messages.append({
                    'filename': f.name,
                    **msg
                })
            except (json.JSONDecodeError, IOError):
                continue
        
        return messages
    
    def get_all_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get all messages across all devices."""
        all_messages = []
        
        for device in ['penguin', 'moto4', 'a9']:
            messages = self.get_message_history(device, limit=limit)
            for msg in messages:
                msg['_device'] = device
                all_messages.append(msg)
        
        # Sort by timestamp
        all_messages.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return all_messages[:limit]
    
    def get_swarm_stats(self) -> Dict[str, Any]:
        """Get overall swarm statistics."""
        device_status = self.get_device_status()
        
        total_messages = 0
        devices_online = 0
        
        for device, status in device_status.items():
            if status.get('online'):
                devices_online += 1
                total_messages += sum(status.get('queues', {}).values())
        
        # Get learning stats if available
        learning_stats = {}
        if self.brain:
            learning_stats = {
                'learned_patterns': len(self.brain.learner.patterns),
                'swarm_votes': len(self.brain.swarm.votes),
            }
        
        return {
            'devices_online': devices_online,
            'total_devices': len(device_status),
            'total_messages': total_messages,
            'timestamp': datetime.now().isoformat(),
            'learning': learning_stats,
        }
    
    def get_learning_suggestions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get pattern learning suggestions."""
        if not self.brain:
            return []
        
        suggestions = self.brain.learner.get_suggestions()
        return [
            {
                'pattern': s['pattern'],
                'category': self.brain.learner._classify_pattern(s['pattern'], s['features']),
                'confidence': s['confidence'],
                'count': s['count'],
            }
            for s in suggestions[:limit]
        ]
    
    def get_consensus_votes(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent consensus votes."""
        if not self.brain:
            return []
        
        votes = []
        for c_hash, vote_data in list(self.brain.swarm.votes.items())[-limit:]:
            # Get the citation
            citation = next(iter(vote_data.values())).get('citation', c_hash)
            consensus = self.brain.swarm.get_consensus(citation)
            
            votes.append({
                'citation': citation,
                'citation_hash': c_hash,
                'consensus': consensus.get('consensus'),
                'confidence': consensus.get('confidence'),
                'quorum': consensus.get('quorum'),
                'vote_count': len(vote_data),
            })
        
        return votes


# HTML Template for Dashboard
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OutClaw Swarm Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0f0f23;
            color: #e0e0e0;
            padding: 20px;
        }
        h1 { color: #00ff88; text-align: center; margin-bottom: 20px; }
        h2 { color: #00aaff; margin-top: 20px; }
        .container { max-width: 1400px; margin: 0 auto; }
        .card {
            background: #1a1a3a;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            border: 1px solid #333;
        }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .status-card { background: #1a1a3a; padding: 15px; border-radius: 8px; }
        .device-card { background: #252540; padding: 15px; border-radius: 8px; margin-bottom: 10px; }
        .online { color: #00ff88; }
        .offline { color: #ff5555; }
        .stat { display: inline-block; margin-right: 15px; }
        .stat-value { font-size: 1.5em; font-weight: bold; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #333; }
        th { background: #252540; color: #00aaff; }
        tr:hover { background: #1f1f3f; }
        .badge { display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 0.85em; }
        .badge-support { background: #004422; color: #00ff88; }
        .badge-oppose { background: #440000; color: #ff8888; }
        .badge-neutral { background: #444400; color: #ffff88; }
        .badge-unknown { background: #444444; color: #cccccc; }
        .timestamp { color: #888; font-size: 0.85em; }
        .refresh-btn {
            background: #00aaff;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 1em;
            margin-bottom: 20px;
        }
        .refresh-btn:hover { background: #00ccff; }
        .message-text { font-family: monospace; font-size: 0.9em; color: #cccccc; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🦅 OutClaw Swarm Dashboard</h1>
        
        <button class="refresh-btn" onclick="refreshDashboard()">🔄 Refresh</button>
        
        <div class="grid">
            <div class="card">
                <h2>📊 Swarm Status</h2>
                <div class="stat"><span class="stat-value">{{ stats.devices_online }}</span> devices online</div>
                <div class="stat"><span class="stat-value">{{ stats.total_messages }}</span> messages</div>
                {% if stats.learning.learned_patterns %}
                <div class="stat"><span class="stat-value">{{ stats.learning.learned_patterns }}</span> patterns learned</div>
                {% endif %}
                <div class="timestamp">Last updated: <span id="last-updated">{{ stats.timestamp }}</span></div>
            </div>
            
            <div class="card">
                <h2>🎯 Quick Actions</h2>
                <ul>
                    <li>📤 Send test message to all devices</li>
                    <li>📥 Pull latest messages</li>
                    <li>📊 View analysis report</li>
                    <li>🎓 Train on new corpus</li>
                </ul>
            </div>
        </div>
        
        <div class="card">
            <h2>🖥️ Device Status</h2>
            {% for device, status in devices.items() %}
            <div class="device-card">
                <h3 style="color: {{ 'green' if status.online else 'red' }}">
                    {{ device.upper() }}
                    <span class="{{ 'online' if status.online else 'offline' }}">
                        {{ 'ONLINE' if status.online else 'OFFLINE' }}
                    </span>
                </h3>
                {% if status.identity %}
                <div style="color: #888; font-size: 0.9em; margin-bottom: 10px;">
                    {{ status.identity.get('hostname', '') }} | 
                    {{ status.identity.get('role', '') }}
                </div>
                {% endif %}
                <div style="margin-top: 10px;">
                    <span class="badge">📥 {{ status.queues.incoming }}</span>
                    <span class="badge">📤 {{ status.queues.outgoing }}</span>
                    <span class="badge">📦 {{ status.queues.archive }}</span>
                </div>
                {% if status.latest_message %}
                <div style="margin-top: 10px; font-size: 0.85em;">
                    Latest: <span class="message-text">{{ status.latest_message.type }}</span>
                    <span class="timestamp">({{ status.latest_message.timestamp }})</span>
                </div>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        
        <div class="card">
            <h2>💡 Pattern Learning</h2>
            {% if suggestions %}
            <table>
                <tr>
                    <th>Pattern</th>
                    <th>Category</th>
                    <th>Confidence</th>
                    <th>Count</th>
                </tr>
                {% for s in suggestions %}
                <tr>
                    <td><code>{{ s.pattern }}</code></td>
                    <td><span class="badge badge-{{ s.category.lower() if s.category else 'unknown' }}">{{ s.category or 'UNKNOWN' }}</span></td>
                    <td>{{ "%.2f"|format(s.confidence) }}</td>
                    <td>{{ s.count }}</td>
                </tr>
                {% endfor %}
            </table>
            {% else %}
            <p>No pattern suggestions yet. Train on some legal text to get started.</p>
            {% endif %}
        </div>
        
        <div class="card">
            <h2>⚖️ Multi-Model Consensus</h2>
            {% if votes %}
            <table>
                <tr>
                    <th>Citation</th>
                    <th>Consensus</th>
                    <th>Confidence</th>
                    <th>Quorum</th>
                    <th>Votes</th>
                </tr>
                {% for v in votes %}
                <tr>
                    <td><code>{{ v.citation[:50] }}...</code></td>
                    <td><span class="badge badge-{{ v.consensus.lower() if v.consensus else 'unknown' }}">{{ v.consensus or 'NONE' }}</span></td>
                    <td>{{ "%.2f"|format(v.confidence) if v.confidence else 'N/A' }}</td>
                    <td>{{ "%.0f%%"|format(v.quorum * 100) if v.quorum else 'N/A' }}</td>
                    <td>{{ v.vote_count }}</td>
                </tr>
                {% endfor %}
            </table>
            {% else %}
            <p>No consensus votes recorded yet. Cast votes from different models to see results.</p>
            {% endif %}
        </div>
        
        <div class="card">
            <h2>📜 Recent Messages</h2>
            {% if messages %}
            <table>
                <tr>
                    <th>Time</th>
                    <th>Device</th>
                    <th>Type</th>
                    <th>Message</th>
                </tr>
                {% for msg in messages %}
                <tr>
                    <td class="timestamp">{{ msg.timestamp[:16] if msg.timestamp else 'N/A' }}</td>
                    <td>{{ msg.get('_device', 'unknown') }}</td>
                    <td><span class="badge">{{ msg.type or 'unknown' }}</span></td>
                    <td><code>{{ (msg.payload|tojson|truncate(50, True)) if msg.payload else (msg.message|truncate(50, True)) }}</code></td>
                </tr>
                {% endfor %}
            </table>
            {% else %}
            <p>No messages yet. Send a test message to get started.</p>
            {% endif %}
        </div>
    </div>
    
    <script>
        function refreshDashboard() {
            location.reload();
        }
        
        // Auto-refresh every 30 seconds
        setTimeout(refreshDashboard, 30000);
    </script>
</body>
</html>
"""


def create_app(monitor: SwarmMonitor):
    """Create the Flask application."""
    app = Flask(__name__)
    
    @app.route('/')
    def dashboard():
        stats = monitor.get_swarm_stats()
        devices = monitor.get_device_status()
        messages = monitor.get_all_messages(limit=20)
        suggestions = monitor.get_learning_suggestions(limit=10)
        votes = monitor.get_consensus_votes(limit=10)
        
        return render_template_string(
            DASHBOARD_TEMPLATE,
            stats=stats,
            devices=devices,
            messages=messages,
            suggestions=suggestions,
            votes=votes,
        )
    
    @app.route('/api/status')
    def api_status():
        return jsonify(monitor.get_swarm_stats())
    
    @app.route('/api/devices')
    def api_devices():
        return jsonify(monitor.get_device_status())
    
    @app.route('/api/messages')
    def api_messages():
        limit = request.args.get('limit', 50, type=int)
        return jsonify(monitor.get_all_messages(limit=limit))
    
    @app.route('/api/suggestions')
    def api_suggestions():
        limit = request.args.get('limit', 10, type=int)
        return jsonify(monitor.get_learning_suggestions(limit=limit))
    
    @app.route('/api/votes')
    def api_votes():
        limit = request.args.get('limit', 10, type=int)
        return jsonify(monitor.get_consensus_votes(limit=limit))
    
    @app.route('/api/send', methods=['POST'])
    def api_send():
        data = request.get_json()
        recipient = data.get('recipient')
        message_type = data.get('type', 'message')
        payload = data.get('payload', {})
        
        if not recipient:
            return jsonify({'error': 'recipient required'}), 400
        
        # Write message to sync bus
        msg_id = f"msg_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(payload)[:8]}"
        envelope = {
            'id': msg_id,
            'sender': 'dashboard',
            'recipient': recipient,
            'type': message_type,
            'timestamp': datetime.now().isoformat(),
            'payload': payload,
        }
        
        # Write to penguin's outgoing
        outgoing_dir = monitor.sync_bus_path / 'penguin' / 'outgoing'
        outgoing_dir.mkdir(parents=True, exist_ok=True)
        
        msg_file = outgoing_dir / f"{recipient}_{msg_id}.json"
        with open(msg_file, 'w') as f:
            json.dump(envelope, f, indent=2)
        
        return jsonify({
            'status': 'queued',
            'message_id': msg_id,
            'file': str(msg_file),
        })
    
    return app


def main():
    """Main entry point."""
    if not HAS_FLASK:
        print("❌ Flask is not installed. Web dashboard requires Flask.")
        print("Install with: pip install flask")
        print("\nAlternatively, use the CLI tools:")
        print("  python3 outclaw_learner.py suggest")
        print("  python3 outclaw_learner.py consensus <citation>")
        sys.exit(1)
    
    monitor = SwarmMonitor()
    app = create_app(monitor)
    
    print("=" * 60)
    print("🦅 OutClaw Swarm Dashboard")
    print("=" * 60)
    print(f"\n📍 Dashboard URL: http://localhost:5000")
    print(f"📁 Sync bus: {monitor.sync_bus_path}")
    print(f"\n🎯 Features:")
    print("   • Real-time device status")
    print("   • Message queue monitoring")
    print("   • Pattern learning visualization")
    print("   • Multi-model consensus tracking")
    print("   • REST API endpoints")
    print(f"\n📊 API Endpoints:")
    print("   GET  /                    - Web dashboard")
    print("   GET  /api/status         - Swarm statistics")
    print("   GET  /api/devices        - Device status")
    print("   GET  /api/messages       - Recent messages")
    print("   GET  /api/suggestions    - Pattern suggestions")
    print("   GET  /api/votes          - Consensus votes")
    print("   POST /api/send           - Send a message")
    print(f"\n🚀 Starting dashboard... (Press Ctrl+C to stop)")
    print("=" * 60)
    
    app.run(host='0.0.0.0', port=5000, debug=False)


if __name__ == "__main__":
    main()

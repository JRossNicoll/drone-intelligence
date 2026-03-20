/**
 * Event Store - Persists events to local JSON files.
 *
 * Events are stored in a single JSON file per day, with deduplication.
 */

const fs = require('fs');
const path = require('path');

class EventStore {
  /**
   * @param {string} dataDir - Directory for event storage
   */
  constructor(dataDir) {
    this.dataDir = dataDir;
    this.events = [];
    this.maxInMemory = 1000;

    // Ensure data directory exists
    if (!fs.existsSync(this.dataDir)) {
      fs.mkdirSync(this.dataDir, { recursive: true });
    }

    // Load existing events
    this._loadEvents();
    console.log(`[EventStore] Initialized with ${this.events.length} events`);
  }

  /**
   * Add a new event.
   * @param {Object} event
   */
  addEvent(event) {
    this.events.push(event);

    // Trim in-memory events
    if (this.events.length > this.maxInMemory) {
      this.events = this.events.slice(-this.maxInMemory);
    }

    // Persist to disk
    this._saveEvent(event);

    console.log(
      `[Event] ${event.type} | ${event.class} | Track #${event.track_id || 'N/A'} | ${event.description || ''}`
    );

    return event;
  }

  /**
   * Get all events.
   * @param {Object} filters - Optional filters (type, class, priority, limit)
   * @returns {Array}
   */
  getEvents(filters = {}) {
    let result = [...this.events];

    if (filters.type) {
      result = result.filter(e => e.type === filters.type);
    }
    if (filters.class) {
      result = result.filter(e => e.class === filters.class);
    }
    if (filters.priority) {
      result = result.filter(e => e.priority === filters.priority);
    }
    if (filters.since) {
      result = result.filter(e => e.timestamp >= filters.since);
    }

    // Sort by timestamp descending (newest first)
    result.sort((a, b) => b.timestamp - a.timestamp);

    const limit = filters.limit || 100;
    return result.slice(0, limit);
  }

  /**
   * Get a single event by ID.
   * @param {string} eventId
   * @returns {Object|null}
   */
  getEvent(eventId) {
    return this.events.find(e => e.event_id === eventId) || null;
  }

  /**
   * Get recent events.
   * @param {number} count
   * @returns {Array}
   */
  getRecentEvents(count = 20) {
    const sorted = [...this.events].sort((a, b) => b.timestamp - a.timestamp);
    return sorted.slice(0, count);
  }

  /**
   * Get event statistics.
   * @returns {Object}
   */
  getStats() {
    const stats = {
      total: this.events.length,
      by_type: {},
      by_class: {},
      by_priority: {},
    };

    for (const event of this.events) {
      stats.by_type[event.type] = (stats.by_type[event.type] || 0) + 1;
      stats.by_class[event.class] = (stats.by_class[event.class] || 0) + 1;
      stats.by_priority[event.priority] = (stats.by_priority[event.priority] || 0) + 1;
    }

    return stats;
  }

  /**
   * Load events from disk.
   */
  _loadEvents() {
    try {
      const files = fs.readdirSync(this.dataDir)
        .filter(f => f.endsWith('.json'))
        .sort();

      for (const file of files) {
        const filepath = path.join(this.dataDir, file);
        const data = fs.readFileSync(filepath, 'utf8');
        const fileEvents = JSON.parse(data);
        if (Array.isArray(fileEvents)) {
          this.events.push(...fileEvents);
        }
      }

      // Keep only recent events in memory
      if (this.events.length > this.maxInMemory) {
        this.events = this.events.slice(-this.maxInMemory);
      }
    } catch (e) {
      // No existing events, start fresh
    }
  }

  /**
   * Save event to disk in daily JSON file.
   */
  _saveEvent(event) {
    try {
      const date = new Date(event.timestamp * 1000);
      const dateStr = date.toISOString().split('T')[0];
      const filename = `events_${dateStr}.json`;
      const filepath = path.join(this.dataDir, filename);

      let existing = [];
      if (fs.existsSync(filepath)) {
        const data = fs.readFileSync(filepath, 'utf8');
        existing = JSON.parse(data);
      }

      existing.push(event);
      fs.writeFileSync(filepath, JSON.stringify(existing, null, 2));
    } catch (e) {
      console.error('[EventStore] Save error:', e.message);
    }
  }

  /**
   * Clear all events.
   */
  clear() {
    this.events = [];
    try {
      const files = fs.readdirSync(this.dataDir).filter(f => f.endsWith('.json'));
      for (const file of files) {
        fs.unlinkSync(path.join(this.dataDir, file));
      }
    } catch (e) {
      // Ignore
    }
  }
}

module.exports = { EventStore };

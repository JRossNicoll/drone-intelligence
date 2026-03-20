/**
 * Rules Engine - Evaluates tracked objects against watchlist rules.
 *
 * Supports conditions:
 * - class: vehicle type match
 * - color: attribute color match
 * - zone: object in specific zone
 * - dwell_time_min: minimum dwell time threshold
 * - direction: movement direction match
 * - min_count: minimum count of class (for person crowding)
 */

const { v4: uuidv4 } = require('uuid');

class RulesEngine {
  /**
   * @param {import('./configManager').ConfigManager} configManager
   * @param {import('./eventStore').EventStore} eventStore
   */
  constructor(configManager, eventStore) {
    this.configManager = configManager;
    this.eventStore = eventStore;

    // Deduplication: track_id + rule_id -> last event timestamp
    this.recentEvents = new Map();
    this.DEDUP_WINDOW_MS = 30000; // 30 second dedup window

    // Person count tracking for count-based rules
    this.lastPersonCount = 0;
    this.personCountAlerted = false;
  }

  /**
   * Evaluate all rules against current frame results.
   * @param {Object} frameResults - Results from vision pipeline
   * @returns {Array} Generated events
   */
  evaluate(frameResults) {
    const rules = this.configManager.getWatchlistRules();
    const trackedObjects = frameResults.tracked_objects || [];
    const personCount = frameResults.person_count || 0;
    const timestamp = frameResults.timestamp;
    const events = [];

    // Clean old dedup entries
    this._cleanDedup(timestamp);

    for (const rule of rules) {
      if (!rule.enabled) continue;

      const conditions = rule.conditions || {};

      // Handle person count rules separately
      if (conditions.min_count && conditions.class &&
          conditions.class.includes('person')) {
        if (personCount >= conditions.min_count) {
          const dedupKey = `count_${rule.id}`;
          if (!this._isDuplicate(dedupKey, timestamp)) {
            const event = this._createEvent(rule, null, {
              person_count: personCount,
              class: 'person',
              attributes: {},
            }, timestamp);
            events.push(event);
            this.recentEvents.set(dedupKey, timestamp);
          }
        }
        continue;
      }

      // Evaluate per tracked object
      for (const obj of trackedObjects) {
        if (this._matchesRule(obj, conditions)) {
          const dedupKey = `${obj.track_id}_${rule.id}`;
          if (!this._isDuplicate(dedupKey, timestamp)) {
            const event = this._createEvent(rule, obj, obj, timestamp);
            events.push(event);
            this.recentEvents.set(dedupKey, timestamp);
          }
        }
      }
    }

    // Process zone events from vision service
    const zoneEvents = frameResults.zone_events || [];
    for (const ze of zoneEvents) {
      const dedupKey = `zone_${ze.track_id}_${ze.zone_id}_${ze.type}`;
      if (!this._isDuplicate(dedupKey, timestamp)) {
        const event = {
          event_id: uuidv4(),
          type: ze.type,
          track_id: ze.track_id,
          zone_id: ze.zone_id,
          class: ze.class || 'unknown',
          attributes: ze.attributes || {},
          timestamp: timestamp,
          priority: 'medium',
          description: `${ze.class || 'Object'} ${ze.type === 'zone_entry' ? 'entered' : 'exited'} ${ze.zone_id}`,
        };
        this.eventStore.addEvent(event);
        events.push(event);
        this.recentEvents.set(dedupKey, timestamp);
      }
    }

    return events;
  }

  /**
   * Check if a tracked object matches rule conditions.
   */
  _matchesRule(obj, conditions) {
    // Class match
    if (conditions.class && conditions.class.length > 0) {
      if (!conditions.class.includes(obj.class)) {
        return false;
      }
    }

    // Color match
    if (conditions.color && conditions.color.length > 0) {
      const objColor = obj.attributes?.color || 'other';
      if (!conditions.color.includes(objColor)) {
        return false;
      }
    }

    // Zone match
    if (conditions.zone && conditions.zone.length > 0) {
      const objZones = obj.zones || [];
      const hasZoneMatch = conditions.zone.some(z => objZones.includes(z));
      if (!hasZoneMatch) {
        return false;
      }
    }

    // Dwell time threshold
    if (conditions.dwell_time_min) {
      const dwellTime = obj.dwell_time || 0;
      if (dwellTime < conditions.dwell_time_min) {
        return false;
      }
    }

    // Direction match
    if (conditions.direction && conditions.direction.length > 0) {
      const objDirection = obj.direction || 'unknown';
      if (!conditions.direction.includes(objDirection)) {
        return false;
      }
    }

    return true;
  }

  /**
   * Create a structured event from a rule match.
   */
  _createEvent(rule, trackedObj, objData, timestamp) {
    const event = {
      event_id: uuidv4(),
      type: rule.event_type || 'watchlist_match',
      rule_id: rule.id,
      rule_name: rule.name,
      track_id: trackedObj?.track_id || null,
      class: objData.class || 'unknown',
      attributes: objData.attributes || {},
      timestamp: timestamp,
      priority: rule.priority || 'medium',
      description: rule.description || rule.name,
    };

    if (trackedObj) {
      event.bbox = trackedObj.bbox;
      event.center = trackedObj.center;
      event.direction = trackedObj.direction;
      event.dwell_time = trackedObj.dwell_time;
      event.zones = trackedObj.zones;
    }

    if (objData.person_count !== undefined) {
      event.person_count = objData.person_count;
    }

    this.eventStore.addEvent(event);
    return event;
  }

  /**
   * Check deduplication.
   */
  _isDuplicate(key, timestamp) {
    const lastTime = this.recentEvents.get(key);
    if (!lastTime) return false;
    return (timestamp - lastTime) * 1000 < this.DEDUP_WINDOW_MS;
  }

  /**
   * Clean old dedup entries.
   */
  _cleanDedup(timestamp) {
    const cutoff = timestamp - this.DEDUP_WINDOW_MS / 1000;
    for (const [key, time] of this.recentEvents.entries()) {
      if (time < cutoff) {
        this.recentEvents.delete(key);
      }
    }
  }
}

module.exports = { RulesEngine };

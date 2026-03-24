/**
 * Configuration Manager - Manages watchlist rules and zone definitions.
 *
 * Reads/writes JSON config files.
 */

const fs = require('fs');

class ConfigManager {
  /**
   * @param {string} watchlistPath - Path to watchlist.json
   * @param {string} zonesPath - Path to zones.json
   */
  constructor(watchlistPath, zonesPath) {
    this.watchlistPath = watchlistPath;
    this.zonesPath = zonesPath;

    this.watchlist = { rules: [] };
    this.zones = { zones: [] };

    this._loadWatchlist();
    this._loadZones();
  }

  /**
   * Get all watchlist rules.
   * @returns {Array}
   */
  getWatchlistRules() {
    return this.watchlist.rules || [];
  }

  /**
   * Get full watchlist config.
   * @returns {Object}
   */
  getWatchlist() {
    return this.watchlist;
  }

  /**
   * Update watchlist with new rules.
   * @param {Object} newWatchlist - Full watchlist object with rules array
   */
  updateWatchlist(newWatchlist) {
    if (newWatchlist.rules && Array.isArray(newWatchlist.rules)) {
      this.watchlist = newWatchlist;
      this._saveWatchlist();
      console.log(`[Config] Watchlist updated: ${newWatchlist.rules.length} rules`);
      return true;
    }
    return false;
  }

  /**
   * Add a single rule to the watchlist.
   * @param {Object} rule
   */
  addRule(rule) {
    if (!rule.id) {
      rule.id = `rule_${Date.now()}`;
    }
    this.watchlist.rules.push(rule);
    this._saveWatchlist();
    return rule;
  }

  /**
   * Remove a rule by ID.
   * @param {string} ruleId
   * @returns {boolean}
   */
  removeRule(ruleId) {
    const idx = this.watchlist.rules.findIndex(r => r.id === ruleId);
    if (idx === -1) return false;
    this.watchlist.rules.splice(idx, 1);
    this._saveWatchlist();
    return true;
  }

  /**
   * Update an existing rule.
   * @param {string} ruleId
   * @param {Object} updates
   * @returns {Object|null}
   */
  updateRule(ruleId, updates) {
    const rule = this.watchlist.rules.find(r => r.id === ruleId);
    if (!rule) return null;
    Object.assign(rule, updates);
    this._saveWatchlist();
    return rule;
  }

  /**
   * Get all zone definitions.
   * @returns {Array}
   */
  getZones() {
    return this.zones.zones || [];
  }

  /**
   * Get full zones config.
   * @returns {Object}
   */
  getZonesConfig() {
    return this.zones;
  }

  /**
   * Update zones configuration.
   * @param {Object} newZones
   */
  updateZones(newZones) {
    if (newZones.zones && Array.isArray(newZones.zones)) {
      this.zones = newZones;
      this._saveZones();
      console.log(`[Config] Zones updated: ${newZones.zones.length} zones`);
      return true;
    }
    return false;
  }

  /**
   * Get combined config.
   * @returns {Object}
   */
  getFullConfig() {
    return {
      watchlist: this.watchlist,
      zones: this.zones,
    };
  }

  _loadWatchlist() {
    try {
      const data = fs.readFileSync(this.watchlistPath, 'utf8');
      this.watchlist = JSON.parse(data);
      console.log(`[Config] Loaded ${this.watchlist.rules?.length || 0} watchlist rules`);
    } catch (e) {
      console.log(`[Config] No watchlist found at ${this.watchlistPath}, using defaults`);
      this.watchlist = { rules: [] };
    }
  }

  _loadZones() {
    try {
      const data = fs.readFileSync(this.zonesPath, 'utf8');
      this.zones = JSON.parse(data);
      console.log(`[Config] Loaded ${this.zones.zones?.length || 0} zones`);
    } catch (e) {
      console.log(`[Config] No zones found at ${this.zonesPath}, using defaults`);
      this.zones = { zones: [] };
    }
  }

  _saveWatchlist() {
    try {
      fs.writeFileSync(this.watchlistPath, JSON.stringify(this.watchlist, null, 2));
    } catch (e) {
      console.error('[Config] Failed to save watchlist:', e.message);
    }
  }

  _saveZones() {
    try {
      fs.writeFileSync(this.zonesPath, JSON.stringify(this.zones, null, 2));
    } catch (e) {
      console.error('[Config] Failed to save zones:', e.message);
    }
  }
}

module.exports = { ConfigManager };

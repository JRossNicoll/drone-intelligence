/**
 * API Routes for the drone intelligence backend.
 */

const express = require('express');

/**
 * Create API router with injected dependencies.
 * @param {import('./configManager').ConfigManager} configManager
 * @param {import('./eventStore').EventStore} eventStore
 * @param {import('./rulesEngine').RulesEngine} rulesEngine
 * @returns {express.Router}
 */
function createApiRoutes(configManager, eventStore, rulesEngine) {
  const router = express.Router();

  // ─── Events ────────────────────────────────────────────────

  /**
   * GET /api/events - List events with optional filters
   * Query params: type, class, priority, limit, since
   */
  router.get('/events', (req, res) => {
    const filters = {
      type: req.query.type || undefined,
      class: req.query.class || undefined,
      priority: req.query.priority || undefined,
      limit: parseInt(req.query.limit) || 100,
      since: req.query.since ? parseFloat(req.query.since) : undefined,
    };

    const events = eventStore.getEvents(filters);
    res.json({
      status: 'ok',
      count: events.length,
      events,
    });
  });

  /**
   * GET /api/events/stats - Event statistics
   */
  router.get('/events/stats', (req, res) => {
    const stats = eventStore.getStats();
    res.json({
      status: 'ok',
      stats,
    });
  });

  /**
   * GET /api/events/:id - Single event details
   */
  router.get('/events/:id', (req, res) => {
    const event = eventStore.getEvent(req.params.id);
    if (!event) {
      return res.status(404).json({ status: 'error', message: 'Event not found' });
    }
    res.json({ status: 'ok', event });
  });

  /**
   * DELETE /api/events - Clear all events
   */
  router.delete('/events', (req, res) => {
    eventStore.clear();
    res.json({ status: 'ok', message: 'All events cleared' });
  });

  // ─── Configuration ─────────────────────────────────────────

  /**
   * GET /api/config - Get full configuration (watchlist + zones)
   */
  router.get('/config', (req, res) => {
    res.json({
      status: 'ok',
      config: configManager.getFullConfig(),
    });
  });

  /**
   * GET /api/config/watchlist - Get watchlist rules
   */
  router.get('/config/watchlist', (req, res) => {
    res.json({
      status: 'ok',
      watchlist: configManager.getWatchlist(),
    });
  });

  /**
   * POST /api/config/watchlist - Update full watchlist
   */
  router.post('/config/watchlist', (req, res) => {
    const success = configManager.updateWatchlist(req.body);
    if (success) {
      res.json({ status: 'ok', message: 'Watchlist updated', watchlist: configManager.getWatchlist() });
    } else {
      res.status(400).json({ status: 'error', message: 'Invalid watchlist format. Expected { rules: [...] }' });
    }
  });

  /**
   * POST /api/config/watchlist/rules - Add a single rule
   */
  router.post('/config/watchlist/rules', (req, res) => {
    const rule = configManager.addRule(req.body);
    res.json({ status: 'ok', message: 'Rule added', rule });
  });

  /**
   * PUT /api/config/watchlist/rules/:id - Update a rule
   */
  router.put('/config/watchlist/rules/:id', (req, res) => {
    const rule = configManager.updateRule(req.params.id, req.body);
    if (rule) {
      res.json({ status: 'ok', message: 'Rule updated', rule });
    } else {
      res.status(404).json({ status: 'error', message: 'Rule not found' });
    }
  });

  /**
   * DELETE /api/config/watchlist/rules/:id - Delete a rule
   */
  router.delete('/config/watchlist/rules/:id', (req, res) => {
    const success = configManager.removeRule(req.params.id);
    if (success) {
      res.json({ status: 'ok', message: 'Rule deleted' });
    } else {
      res.status(404).json({ status: 'error', message: 'Rule not found' });
    }
  });

  /**
   * GET /api/config/zones - Get zone definitions
   */
  router.get('/config/zones', (req, res) => {
    res.json({
      status: 'ok',
      zones: configManager.getZonesConfig(),
    });
  });

  /**
   * POST /api/config/zones - Update zones
   */
  router.post('/config/zones', (req, res) => {
    const success = configManager.updateZones(req.body);
    if (success) {
      res.json({ status: 'ok', message: 'Zones updated', zones: configManager.getZonesConfig() });
    } else {
      res.status(400).json({ status: 'error', message: 'Invalid zones format. Expected { zones: [...] }' });
    }
  });

  // ─── Health ────────────────────────────────────────────────

  /**
   * GET /api/health - Backend health check
   */
  router.get('/health', (req, res) => {
    res.json({
      status: 'ok',
      uptime: process.uptime(),
      events_count: eventStore.events.length,
      rules_count: configManager.getWatchlistRules().length,
      zones_count: configManager.getZones().length,
    });
  });

  return router;
}

module.exports = { createApiRoutes };

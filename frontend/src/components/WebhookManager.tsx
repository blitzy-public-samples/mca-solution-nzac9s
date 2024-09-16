import React, { useState, useEffect } from 'react';
import { getWebhooks, createWebhook, deleteWebhook } from '@/services/api';
import { validateUrl } from '@/utils/validators';

// HUMAN ASSISTANCE NEEDED
// This component requires additional refinement and error handling for production readiness.
// The confidence level is low (0.5), so human review and adjustments are necessary.

const WebhookManager: React.FC = () => {
  const [webhooks, setWebhooks] = useState<Array<{ id: string; url: string }>>([]);
  const [newWebhookUrl, setNewWebhookUrl] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    fetchWebhooks();
  }, []);

  const fetchWebhooks = async () => {
    try {
      const fetchedWebhooks = await getWebhooks();
      setWebhooks(fetchedWebhooks);
    } catch (error) {
      setMessage('Failed to fetch webhooks');
    }
  };

  const handleAddWebhook = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateUrl(newWebhookUrl)) {
      setMessage('Invalid URL format');
      return;
    }
    try {
      await createWebhook(newWebhookUrl);
      setNewWebhookUrl('');
      fetchWebhooks();
      setMessage('Webhook added successfully');
    } catch (error) {
      setMessage('Failed to add webhook');
    }
  };

  const handleDeleteWebhook = async (id: string) => {
    try {
      await deleteWebhook(id);
      fetchWebhooks();
      setMessage('Webhook deleted successfully');
    } catch (error) {
      setMessage('Failed to delete webhook');
    }
  };

  // HUMAN ASSISTANCE NEEDED
  // Implement webhook testing functionality

  return (
    <div>
      <h2>Webhook Manager</h2>
      {message && <p>{message}</p>}
      <form onSubmit={handleAddWebhook}>
        <input
          type="text"
          value={newWebhookUrl}
          onChange={(e) => setNewWebhookUrl(e.target.value)}
          placeholder="Enter webhook URL"
        />
        <button type="submit">Add Webhook</button>
      </form>
      <ul>
        {webhooks.map((webhook) => (
          <li key={webhook.id}>
            {webhook.url}
            <button onClick={() => handleDeleteWebhook(webhook.id)}>Delete</button>
            {/* HUMAN ASSISTANCE NEEDED: Add test webhook button */}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default WebhookManager;
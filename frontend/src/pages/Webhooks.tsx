import React, { useState, useEffect } from 'react';
import { WebhookManager } from '@/components/WebhookManager';
import { getWebhooks, createWebhook, deleteWebhook } from '@/services/api';

// HUMAN ASSISTANCE NEEDED
// The following code may need additional error handling, loading states, and potentially pagination for production readiness.
// Also, the confidence level is below 0.8, so please review and adjust as necessary.

const Webhooks: React.FC = () => {
  const [webhooks, setWebhooks] = useState<any[]>([]);

  useEffect(() => {
    fetchWebhooks();
  }, []);

  const fetchWebhooks = async () => {
    try {
      const data = await getWebhooks();
      setWebhooks(data);
    } catch (error) {
      console.error('Error fetching webhooks:', error);
      // TODO: Implement proper error handling
    }
  };

  const handleAddWebhook = async (webhookData: any) => {
    try {
      const newWebhook = await createWebhook(webhookData);
      setWebhooks([...webhooks, newWebhook]);
    } catch (error) {
      console.error('Error creating webhook:', error);
      // TODO: Implement proper error handling
    }
  };

  const handleDeleteWebhook = async (webhookId: string) => {
    try {
      await deleteWebhook(webhookId);
      setWebhooks(webhooks.filter(webhook => webhook.id !== webhookId));
    } catch (error) {
      console.error('Error deleting webhook:', error);
      // TODO: Implement proper error handling
    }
  };

  return (
    <div>
      <h1>Manage Webhooks</h1>
      <WebhookManager
        webhooks={webhooks}
        onAddWebhook={handleAddWebhook}
        onDeleteWebhook={handleDeleteWebhook}
      />
    </div>
  );
};

export default Webhooks;
import React, { useEffect, useState, Fragment } from 'react';
import { Listbox, Transition } from '@headlessui/react';
import { CheckIcon, ChevronUpDownIcon } from '@heroicons/react/20/solid';
import { Model, Service, ModelsResponse } from '../../types';
import api from '../../services/api';

interface ModelSelectorProps {
  selectedModel: string;
  selectedService?: string;
  onModelChange: (model: string, service?: string) => void;
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({
  selectedModel,
  selectedService,
  onModelChange,
}) => {
  const [models, setModels] = useState<Model[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [defaultService, setDefaultService] = useState<string>('');
  const [defaultModel, setDefaultModel] = useState<string>('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    loadModels();
  }, []);

  // Effect to handle selectedModel changes and ensure default is set
  useEffect(() => {
    if (!selectedModel && models.length > 0) {
      // Try to set default model from API call
      loadModels();
    }
  }, [selectedModel, models.length]);

  const loadModels = async () => {
    try {
      const response = await api.getModels() as ModelsResponse;
      setModels(response.models);
      setServices(response.services);
      setDefaultService(response.default_service);
      setDefaultModel(response.default_model);
      
      // Set default model and service if none selected
      if (!selectedModel && response.default_model) {
        const defaultModelInfo = response.models.find(m => m.is_default);
        if (defaultModelInfo) {
          console.log('ModelSelector: Setting default model:', defaultModelInfo.name, 'service:', defaultModelInfo.service);
          onModelChange(defaultModelInfo.name, defaultModelInfo.service);
        } else if (response.default_model) {
          // Fallback to just the model name
          onModelChange(response.default_model, response.default_service);
        }
      }
    } catch (error) {
      console.error('Failed to load models:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const selectedModelData = models.find((m) => m.name === selectedModel);

  if (isLoading) {
    return (
      <div className="w-64">
        <div className="h-10 bg-gray-200 animate-pulse rounded-lg"></div>
      </div>
    );
  }

  const handleModelChange = (modelName: string) => {
    const model = models.find(m => m.name === modelName);
    if (model) {
      onModelChange(model.name, model.service);
    }
  };

  // Group models by service for better organization
  const modelsByService = services.map(service => ({
    service,
    models: models.filter(m => m.service === service.name)
  }));

  return (
    <Listbox value={selectedModel} onChange={handleModelChange}>
      <div className="relative w-64">
        <Listbox.Button className="relative w-full cursor-pointer rounded-lg bg-white py-2 pl-3 pr-10 text-left border border-gray-300 focus:outline-none focus-visible:border-primary-500 focus-visible:ring-2 focus-visible:ring-white focus-visible:ring-opacity-75 focus-visible:ring-offset-2 focus-visible:ring-offset-primary-300 sm:text-sm">
          <span className="block truncate">
            {selectedModelData?.name || 'Select a model'}
          </span>
          <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
            <ChevronUpDownIcon
              className="h-5 w-5 text-gray-400"
              aria-hidden="true"
            />
          </span>
        </Listbox.Button>
        
        <Transition
          as={Fragment}
          leave="transition ease-in duration-100"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <Listbox.Options className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md bg-white py-1 text-base shadow-lg ring-1 ring-black ring-opacity-5 focus:outline-none sm:text-sm">
            {models.map((model) => (
              <Listbox.Option
                key={`${model.service}:${model.name}`}
                className={({ active }) =>
                  `relative cursor-pointer select-none py-2 pl-10 pr-4 ${
                    active ? 'bg-primary-100 text-primary-900' : 'text-gray-900'
                  } ${!model.available ? 'opacity-50' : ''}`
                }
                value={model.name}
                disabled={!model.available}
              >
                {({ selected }) => (
                  <>
                    <div>
                      <span
                        className={`block truncate ${
                          selected ? 'font-medium' : 'font-normal'
                        }`}
                      >
                        {model.name}
                        {model.is_default && (
                          <span className="ml-2 text-xs text-primary-600">
                            (default)
                          </span>
                        )}
                      </span>
                      <span className="text-xs text-gray-500">
                        {model.service} • {model.service_type}
                        {!model.available && ' • Offline'}
                      </span>
                    </div>
                    {selected ? (
                      <span className="absolute inset-y-0 left-0 flex items-center pl-3 text-primary-600">
                        <CheckIcon className="h-5 w-5" aria-hidden="true" />
                      </span>
                    ) : null}
                  </>
                )}
              </Listbox.Option>
            ))}
          </Listbox.Options>
        </Transition>
      </div>
    </Listbox>
  );
};
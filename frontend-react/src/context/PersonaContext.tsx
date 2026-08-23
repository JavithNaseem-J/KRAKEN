import React, { createContext, useContext, useState } from 'react';

export type PersonaRole = 'end_user' | 'tier1_analyst' | 'incident_commander' | 'admin';

export interface Persona {
  id: string;
  name: string;
  role: PersonaRole;
  label: string;
  badge: string;
  title: string;
  description: string;
  apiKey: string;
  canApprove: boolean;
  clearanceLevel: 'PUBLIC' | 'TIER_1' | 'TIER_2' | 'ADMIN';
}

/**
 * Ordered strictly from lowest privilege to highest privilege:
 * 1. User (End User)
 * 2. Alice (Tier 1 Analyst)
 * 3. Bob (Security Lead / Incident Commander)
 * 4. Admin (Approver / CISO)
 */
export const PERSONAS: Persona[] = [
  {
    id: 'user',
    name: 'User',
    role: 'end_user',
    label: 'User',
    badge: 'User',
    title: 'End User',
    description: 'General IT inquiries and personal ticket status. Cannot trigger operational actions.',
    apiKey: import.meta.env.VITE_API_KEY_ALICE ?? 'dev-key-alice-longer-secure-key',
    canApprove: false,
    clearanceLevel: 'PUBLIC',
  },
  {
    id: 'alice',
    name: 'Alice',
    role: 'tier1_analyst',
    label: 'Alice',
    badge: 'Tier 1',
    title: 'Tier 1 Analyst',
    description: 'Alert triage, ticket search, stages containment requests (cannot authorize execution).',
    apiKey: import.meta.env.VITE_API_KEY_ALICE ?? 'dev-key-alice-longer-secure-key',
    canApprove: false,
    clearanceLevel: 'TIER_1',
  },
  {
    id: 'bob',
    name: 'Bob',
    role: 'incident_commander',
    label: 'Bob',
    badge: 'Lead',
    title: 'Security Lead',
    description: 'Authorizes perimeter containment (IP quarantine, account unlock) and inspects forensic SOPs.',
    apiKey: import.meta.env.VITE_API_KEY_BOB ?? 'dev-key-bob-longer-secure-key',
    canApprove: true,
    clearanceLevel: 'TIER_2',
  },
  {
    id: 'admin',
    name: 'Admin',
    role: 'admin',
    label: 'Admin',
    badge: 'Admin',
    title: 'Approver',
    description: 'Unrestricted enterprise clearance, policy override, full cryptographic audit trail inspection.',
    apiKey:
      import.meta.env.VITE_API_KEY_ADMIN ??
      import.meta.env.VITE_API_KEY_ALICE ??
      'dev-key-alice-longer-secure-key',
    canApprove: true,
    clearanceLevel: 'ADMIN',
  },
];

interface PersonaContextType {
  activePersona: Persona;
  setPersona: (role: PersonaRole) => void;
  personas: Persona[];
}

const PERSONA_STORAGE_KEY = 'kraken.secops.active_persona.v1';

const PersonaContext = createContext<PersonaContextType | undefined>(undefined);

export const PersonaProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [activePersona, setActivePersona] = useState<Persona>(() => {
    try {
      const saved = localStorage.getItem(PERSONA_STORAGE_KEY);
      const found = PERSONAS.find((p) => p.role === saved);
      // Default to Alice (Tier 1 Analyst) for primary triage workflow
      return found || PERSONAS.find((p) => p.role === 'tier1_analyst') || PERSONAS[0];
    } catch {
      return PERSONAS.find((p) => p.role === 'tier1_analyst') || PERSONAS[0];
    }
  });

  const setPersona = (role: PersonaRole) => {
    const target = PERSONAS.find((p) => p.role === role);
    if (target) {
      setActivePersona(target);
      localStorage.setItem(PERSONA_STORAGE_KEY, role);
    }
  };

  return (
    <PersonaContext.Provider value={{ activePersona, setPersona, personas: PERSONAS }}>
      {children}
    </PersonaContext.Provider>
  );
};

export const usePersona = (): PersonaContextType => {
  const context = useContext(PersonaContext);
  if (!context) {
    throw new Error('usePersona must be used within a PersonaProvider');
  }
  return context;
};
